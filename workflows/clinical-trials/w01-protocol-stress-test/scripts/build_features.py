#!/usr/bin/env python3
"""Build the patient-level feature table at the index date.

Reads every shard folder under --population (Synthea CSVs) and the
`features` / `prescreen` blocks of the reviewed rule set, and writes:
  features.parquet  one row per patient alive at the index date
  prescreen.json    population counts, prescreened composition, data coverage
                    and the per-shard Synthea provenance

Feature kinds (see criteria.reviewed.json):
  lab_latest        latest value on or before the index date (+ <f>_days_ago),
                    optionally restricted to one `units` string
  ckd_epi_2021      CKD-EPI 2021 eGFR from the latest creatinine (+ _days_ago)
  lab_max_before    max value measured at least `min_days_ago` days before index
  obs_latest_text   latest text value (+ _days_ago)
  condition_active  condition started on/before index and not stopped by then
  condition_ever    condition (or procedure) started on/before index
  event_days_since  days since the most recent onset (null if never)
  med_days_on       days on a currently active prescription (0 if none)
  med_days_since    0 if active at index, else days since last stop (null if never)

Usage:
    python build_features.py --population population/ --rules criteria.json \
        --config config.json --features features.parquet --prescreen prescreen.json
    python build_features.py --selftest
"""

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import polars as pl

DATE = lambda c: pl.col(c).str.slice(0, 10).str.to_date(strict=False)  # noqa: E731


def _codes(spec: dict) -> list[str]:
    return [c for v in spec.get("codes", {}).values() for c in v]


def _match(spec: dict) -> pl.Expr:
    expr = pl.col("CODE").is_in(_codes(spec))
    if spec.get("description_regex"):
        expr = expr | pl.col("DESCRIPTION").str.contains(spec["description_regex"])
    return expr


def load(pop_dir: Path, needed_obs: list[str]) -> dict[str, pl.DataFrame]:
    shards = sorted(p for p in pop_dir.iterdir() if (p / "patients.csv").exists())
    if not shards:
        raise SystemExit(f"build_features: no shard with patients.csv under {pop_dir}")

    def cat(table, cols, filt=None):
        frames = []
        for s in shards:
            lf = pl.scan_csv(s / f"{table}.csv", infer_schema_length=0).select(cols)
            frames.append((lf.filter(filt) if filt is not None else lf).collect())
        return pl.concat(frames)

    t = {
        "patients": cat("patients", ["Id", "BIRTHDATE", "DEATHDATE", "RACE", "ETHNICITY", "GENDER"]),
        "observations": cat("observations", ["DATE", "PATIENT", "CODE", "VALUE", "UNITS"], pl.col("CODE").is_in(needed_obs)),
        "conditions": cat("conditions", ["START", "STOP", "PATIENT", "CODE"]),
        "procedures": cat("procedures", ["START", "STOP", "PATIENT", "CODE"]),
        "medications": cat("medications", ["START", "STOP", "PATIENT", "CODE", "DESCRIPTION"]),
    }
    t["shards"] = [json.loads((s / "provenance.json").read_text()) if (s / "provenance.json").exists() else {} for s in shards]
    return t


def ckd_epi_2021(scr: pl.Expr, age: pl.Expr, female: pl.Expr) -> pl.Expr:
    """CKD-EPI 2021 race-free creatinine equation (Inker et al., NEJM 2021)."""
    kappa = pl.when(female).then(0.7).otherwise(0.9)
    alpha = pl.when(female).then(-0.241).otherwise(-0.302)
    r = scr / kappa
    return (
        142
        * pl.min_horizontal(r, pl.lit(1.0)).pow(alpha)
        * pl.max_horizontal(r, pl.lit(1.0)).pow(-1.200)
        * pl.lit(0.9938).pow(age)
        * pl.when(female).then(1.012).otherwise(1.0)
    )


def build(t: dict, rules: dict, index: date) -> pl.DataFrame:
    idx = pl.lit(index)
    pats = (
        t["patients"]
        .with_columns(birth=DATE("BIRTHDATE"), death=DATE("DEATHDATE"))
        .filter((pl.col("birth") <= idx) & (pl.col("death").is_null() | (pl.col("death") > idx)))
        .select(
            patient_id="Id",
            age=(idx - pl.col("birth")).dt.total_days() / 365.25,
            birth="birth",
            sex="GENDER",
            race="RACE",
            ethnicity="ETHNICITY",
            race_eth=pl.when(pl.col("ETHNICITY") == "hispanic").then(pl.lit("hispanic")).otherwise(pl.col("RACE")),
        )
    )
    if pats["patient_id"].n_unique() != pats.height:
        raise SystemExit("build_features: duplicate patient ids across shards")

    obs = t["observations"].with_columns(d=DATE("DATE")).filter(pl.col("d") <= idx).with_columns(
        days_ago=(idx - pl.col("d")).dt.total_days()
    )
    sources = {"conditions": t["conditions"], "procedures": t["procedures"]}
    meds = t["medications"].with_columns(s=DATE("START"), e=DATE("STOP")).filter(pl.col("s") <= idx)

    out = pats
    for name, spec in rules["features"].items():
        kind = spec["kind"]
        if kind in ("lab_latest", "ckd_epi_2021", "obs_latest_text"):
            o = obs.filter(pl.col("CODE").is_in(_codes(spec)))
            if spec.get("units"):  # Synthea reuses 33914-3 for two different GFR series
                o = o.filter(pl.col("UNITS") == spec["units"])
            o = o.sort("PATIENT", "d", "VALUE").group_by("PATIENT", maintain_order=True).last()  # VALUE breaks same-day ties deterministically
            if kind == "obs_latest_text":
                val = pl.col("VALUE")
            else:
                val = pl.col("VALUE").cast(pl.Float64, strict=False)
            f = o.select(patient_id="PATIENT", **{name: val, f"{name}_days_ago": "days_ago", f"_{name}_date": "d"})
            out = out.join(f, on="patient_id", how="left")
            if kind == "ckd_epi_2021":
                age_at = (pl.col(f"_{name}_date") - pl.col("birth")).dt.total_days() / 365.25
                out = out.with_columns(ckd_epi_2021(pl.col(name), age_at, pl.col("sex") == "F").alias(name))
            out = out.drop(f"_{name}_date")
        elif kind == "lab_max_before":
            f = (
                obs.filter(pl.col("CODE").is_in(_codes(spec)) & (pl.col("days_ago") >= spec["min_days_ago"]))
                .group_by("PATIENT")
                .agg(pl.col("VALUE").cast(pl.Float64, strict=False).max().alias(name))
                .rename({"PATIENT": "patient_id"})
            )
            out = out.join(f, on="patient_id", how="left")
        elif kind in ("condition_active", "condition_ever", "event_days_since"):
            src = spec["source"] if isinstance(spec["source"], list) else [spec["source"]]
            ev = pl.concat([sources[s] for s in src]).with_columns(s=DATE("START"), e=DATE("STOP"))
            ev = ev.filter(pl.col("CODE").is_in(_codes(spec)) & (pl.col("s") <= idx))
            if kind == "condition_active":
                ev = ev.filter(pl.col("e").is_null() | (pl.col("e") > idx))
            if kind == "event_days_since":
                f = ev.group_by("PATIENT").agg((idx - pl.col("s").max()).dt.total_days().alias(name))
            else:
                f = ev.select(pl.col("PATIENT").unique()).with_columns(pl.lit(True).alias(name))
            out = out.join(f.rename({"PATIENT": "patient_id"}), on="patient_id", how="left")
            if kind != "event_days_since":
                out = out.with_columns(pl.col(name).fill_null(False))
        elif kind in ("med_days_on", "med_days_since"):
            m = meds.filter(_match(spec))
            active = pl.col("e").is_null() | (pl.col("e") > idx)
            if kind == "med_days_on":
                # shortcut: back-to-back refills are not chained; upgrade if a source splits long courses.
                f = m.filter(active).group_by("PATIENT").agg((idx - pl.col("s").min()).dt.total_days().alias(name))
            else:
                f = m.group_by("PATIENT").agg(
                    pl.when(active.any()).then(0).otherwise((idx - pl.col("e").max()).dt.total_days()).alias(name)
                )
            out = out.join(f.rename({"PATIENT": "patient_id"}), on="patient_id", how="left")
            if kind == "med_days_on":
                out = out.with_columns(pl.col(name).fill_null(0))
        else:
            raise SystemExit(f"build_features: unknown feature kind {kind!r} for {name}")
    return out.drop("birth").with_columns(prescreened=prescreen_expr(rules["prescreen"]["rules"])).sort("patient_id")


def prescreen_expr(rules: list[dict]) -> pl.Expr:
    expr = pl.lit(True)
    for r in rules:
        c = pl.col(r["field"])
        if r["operator"] == "is_true":
            expr = expr & c.fill_null(False)
        elif r["operator"] == "gte":
            expr = expr & (c >= r["value"]).fill_null(False)
        else:
            raise SystemExit(f"build_features: unsupported prescreen operator {r['operator']!r}")
    return expr


def summarize(df: pl.DataFrame, t: dict, rules: dict, index: date) -> dict:
    pre = df.filter(pl.col("prescreened"))
    n = pre.height
    share = lambda e: round(pre.select(e.mean()).item(), 4) if n else None  # noqa: E731
    return {
        "index_date": index.isoformat(),
        "n_patients_generated": t["patients"].height,
        "n_alive_at_index": df.height,
        "n_adults": df.filter(pl.col("age") >= 18).height,
        "n_prescreened": n,
        "prescreened_composition": {
            "female": share(pl.col("sex") == "F"),
            "age_ge_65": share(pl.col("age") >= 65),
            "age_ge_75": share(pl.col("age") >= 75),
            "t2d": share(pl.col("t2d")) if "t2d" in pre.columns else None,
            "race_eth": {k: round(v / n, 4) for k, v in sorted(pre["race_eth"].value_counts().iter_rows())} if n else {},
        },
        # Non-null values for measurements; patients flagged True for boolean features.
        "prescreened_coverage": {f: int(pre[f].sum() if pre[f].dtype == pl.Boolean else pre[f].is_not_null().sum()) for f in rules["features"]},
        "shards": t["shards"],
    }


def run(args) -> int:
    rules = json.loads(Path(args.rules).read_text())
    cfg = json.loads(Path(args.config).read_text())
    index = date.fromisoformat(cfg["index_date"])
    needed = sorted({c for s in rules["features"].values() if s["source"] == "observations" for c in _codes(s)})
    t = load(Path(args.population), needed)
    df = build(t, rules, index)
    Path(args.features).parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(args.features)
    summary = summarize(df, t, rules, index)
    Path(args.prescreen).write_text(json.dumps(summary, indent=2) + "\n")
    print(f"build_features: {summary['n_alive_at_index']} patients alive at {index}, {summary['n_prescreened']} prescreened")
    return 0


def _selftest() -> int:
    rules = {
        "features": {
            "egfr": {"kind": "ckd_epi_2021", "source": "observations", "codes": {"loinc": ["2160-0"]}},
            "uacr": {"kind": "lab_latest", "source": "observations", "codes": {"loinc": ["14959-1"]}},
            "gfr": {"kind": "lab_latest", "source": "observations", "codes": {"loinc": ["33914-3"]}, "units": "mL/min/{1.73_m2}"},
            "uacr_old": {"kind": "lab_max_before", "source": "observations", "codes": {"loinc": ["14959-1"]}, "min_days_ago": 90},
            "nyha": {"kind": "obs_latest_text", "source": "observations", "codes": {"loinc": ["88020-3"]}},
            "ckd": {"kind": "condition_active", "source": "conditions", "codes": {"snomed": ["433144002"]}},
            "tx": {"kind": "condition_ever", "source": ["conditions", "procedures"], "codes": {"snomed": ["70536003"]}},
            "cv": {"kind": "event_days_since", "source": "conditions", "codes": {"snomed": ["22298006"]}},
            "ace": {"kind": "med_days_on", "source": "medications", "description_regex": "(?i)pril\\b"},
            "sglt2": {"kind": "med_days_since", "source": "medications", "codes": {"rxnorm": ["1373463"]}},
        },
        "prescreen": {"rules": [{"field": "ckd", "operator": "is_true"}, {"field": "age", "operator": "gte", "value": 18}]},
    }
    csv = {
        "patients": "Id,BIRTHDATE,DEATHDATE,RACE,ETHNICITY,GENDER\nA,1960-01-01,,white,nonhispanic,F\nB,1950-01-01,,black,hispanic,M\nC,1950-01-01,2020-01-01,white,nonhispanic,M\nD,2015-01-01,,asian,nonhispanic,F\n",
        "observations": "DATE,PATIENT,ENCOUNTER,CATEGORY,CODE,DESCRIPTION,VALUE,UNITS,TYPE\n"
        "2025-06-01T00:00:00Z,A,e,l,2160-0,Cr,2.0,mg/dL,numeric\n2025-12-01T00:00:00Z,A,e,l,2160-0,Cr,1.0,mg/dL,numeric\n"
        "2025-01-01T00:00:00Z,A,e,l,14959-1,UACR,250,mg/g,numeric\n2025-12-15T00:00:00Z,A,e,l,14959-1,UACR,40,mg/g,numeric\n"
        "2026-03-01T00:00:00Z,A,e,l,14959-1,UACR,999,mg/g,numeric\n"
        "2025-12-01T00:00:00Z,A,e,l,33914-3,GFR,44,mL/min/{1.73_m2},numeric\n2025-12-20T00:00:00Z,A,e,l,33914-3,GFR,12,mL/min,numeric\n2025-11-01T00:00:00Z,B,e,s,88020-3,NYHA,Class IV,,text\n",
        "conditions": "START,STOP,PATIENT,ENCOUNTER,SYSTEM,CODE,DESCRIPTION\n2020-01-01,,A,e,S,433144002,CKD3\n2020-01-01,2024-01-01,B,e,S,433144002,CKD3\n2025-12-02,,B,e,S,22298006,MI\n",
        "procedures": "START,STOP,PATIENT,ENCOUNTER,SYSTEM,CODE,DESCRIPTION,BASE_COST,REASONCODE,REASONDESCRIPTION\n2010-01-01T00:00:00Z,,B,e,S,70536003,Kidney tx,0,,\n",
        "medications": "START,STOP,PATIENT,PAYER,ENCOUNTER,CODE,DESCRIPTION,BASE_COST,PAYER_COVERAGE,DISPENSES,TOTALCOST,REASONCODE,REASONDESCRIPTION\n"
        "2025-11-01T00:00:00Z,,A,p,e,314076,lisinopril 10 MG Oral Tablet,1,1,1,1,,\n2025-10-01T00:00:00Z,2025-12-01T00:00:00Z,B,p,e,1373463,canagliflozin 100 MG,1,1,1,1,,\n",
    }
    with tempfile.TemporaryDirectory() as tmp:
        shard = Path(tmp) / "pop" / "00"
        shard.mkdir(parents=True)
        for k, v in csv.items():
            (shard / f"{k}.csv").write_text(v)
        t = load(Path(tmp) / "pop", ["2160-0", "14959-1", "88020-3", "33914-3"])
        df = build(t, rules, date(2026, 1, 1))
        r = {row["patient_id"]: row for row in df.to_dicts()}
        assert set(r) == {"A", "B", "D"}, r.keys()  # C died before index
        a, b = r["A"], r["B"]
        assert abs(a["egfr"] - 62.16) < 0.01, a["egfr"]  # Cr 1.0 mg/dL, female, 65.9 y: 142*(1/0.7)^-1.2*0.9938^65.9*1.012
        assert a["uacr"] == 40 and a["uacr_days_ago"] == 17  # post-index value ignored
        assert a["gfr"] == 44  # the later mL/min value is a different series
        assert a["uacr_old"] == 250 and b["uacr_old"] is None
        assert b["nyha"] == "Class IV" and a["nyha"] is None
        assert a["ckd"] and not b["ckd"] and b["tx"] and not a["tx"]
        assert b["cv"] == 30 and a["cv"] is None
        assert a["ace"] == 61 and b["ace"] == 0
        assert b["sglt2"] == 31 and a["sglt2"] is None
        assert a["prescreened"] and not b["prescreened"] and not r["D"]["prescreened"]
        assert b["race_eth"] == "hispanic"
        s = summarize(df, t, rules, date(2026, 1, 1))
        assert s["n_prescreened"] == 1 and s["n_alive_at_index"] == 3
    print("build_features selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("--population", "--rules", "--config", "--features", "--prescreen"):
        ap.add_argument(a)
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not all((a.population, a.rules, a.config, a.features, a.prescreen)):
        ap.error("--population, --rules, --config, --features and --prescreen are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
