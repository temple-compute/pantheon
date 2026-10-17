#!/usr/bin/env python3
"""Evaluate one batch of protocol variants against the prescreened population.

One boolean pass-mask is computed per (criterion, value) and cached; a
variant's eligible set is the AND of the masks of the criteria it applies.

Missing data: an inclusion criterion fails when its field is missing (no
evidence of eligibility); an exclusion criterion passes when its field is
missing (no evidence of the excluding condition).

Metrics per variant (all over the prescreened population P):
  n_eligible, eligible_share = n_eligible / |P|, sf_proxy = 1 - eligible_share
  female, age_ge_65, age_ge_75, share_<race_eth>   composition of the eligible set
  gini_simpson = 1 - sum_k p_k^2 over race/ethnicity groups (null if n_eligible < 2)
  fail_<id>  prescreened patients failing criterion <id> (null if not applied)
  sole_<id>  prescreened patients failing only <id> among the applied criteria

Usage:
    python evaluate.py --batch batch_000.json --features features.parquet \
        --rules criteria.json --out evaluated/00/
    python evaluate.py --selftest
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import polars as pl


def condition(df: pl.DataFrame, c: dict, value) -> np.ndarray:
    """True where the criterion's condition holds (before inclusion/exclusion polarity)."""
    col = df[c["field"]]
    op = c["operator"]
    if op == "between":
        e = col.is_between(value[0], value[1])
    elif op == "gte":
        e = col >= value
    elif op == "within_days":
        e = col <= value
    elif op == "is_true":
        e = col
    elif op == "equals":
        e = col == value
    else:
        raise SystemExit(f"evaluate: unknown operator {op!r} in {c['id']}")
    if c.get("lookback_days") is not None:
        e = e & (df[f"{c['field']}_days_ago"] <= c["lookback_days"])
    return e.fill_null(False).to_numpy().astype(bool)


def pass_mask(df: pl.DataFrame, c: dict, value) -> np.ndarray:
    cond = condition(df, c, value)
    return cond if c["type"] == "inclusion" else ~cond


def evaluate(variants: list[dict], df: pl.DataFrame, rules: dict) -> list[dict]:
    pre = df.filter(pl.col("prescreened")).sort("patient_id")
    crit = {c["id"]: c for c in rules["criteria"] if c.get("computable")}
    groups = sorted(pre["race_eth"].unique().to_list())
    race = pre["race_eth"].to_numpy()
    race_onehot = np.stack([race == g for g in groups]) if groups else np.zeros((0, pre.height), bool)
    female = (pre["sex"] == "F").to_numpy()
    age = pre["age"].to_numpy()
    n_pre = pre.height
    cache: dict[tuple, np.ndarray] = {}
    rows = []
    for v in variants:
        ids = [cid for cid in crit if cid in v["params"]]
        masks = []
        for cid in ids:
            key = (cid, json.dumps(v["params"][cid]))
            if key not in cache:
                cache[key] = pass_mask(pre, crit[cid], v["params"][cid])
            masks.append(cache[key])
        m = np.stack(masks) if masks else np.ones((0, n_pre), bool)
        elig = m.all(axis=0) if masks else np.ones(n_pre, bool)
        n_fail = (~m).sum(axis=0)
        n = int(elig.sum())
        counts = race_onehot[:, elig].sum(axis=1) if groups else np.array([])
        p = counts / n if n else counts
        row = {
            "variant_id": v["variant_id"], "hash": v["hash"], "kind": v["kind"], "label": v["label"],
            "n_prescreened": n_pre, "n_eligible": n,
            "eligible_share": n / n_pre if n_pre else None,
            "sf_proxy": 1 - n / n_pre if n_pre else None,
            "female": float(female[elig].mean()) if n else None,
            "age_ge_65": float((age[elig] >= 65).mean()) if n else None,
            "age_ge_75": float((age[elig] >= 75).mean()) if n else None,
            "gini_simpson": float(1 - (p**2).sum()) if n >= 2 else None,
            **{f"share_{g}": (float(p[i]) if n else None) for i, g in enumerate(groups)},
        }
        for cid in crit:
            if cid in v["params"]:
                k = ids.index(cid)
                row[f"fail_{cid}"] = int((~m[k]).sum())
                row[f"sole_{cid}"] = int(((~m[k]) & (n_fail == 1)).sum())
            else:
                row[f"fail_{cid}"] = row[f"sole_{cid}"] = None
        row["params"] = json.dumps(v["params"], sort_keys=True)
        rows.append(row)
    return rows


def run(args) -> int:
    variants = json.loads(Path(args.batch).read_text())
    df = pl.read_parquet(args.features)
    rules = json.loads(Path(args.rules).read_text())
    rows = evaluate(variants, df, rules)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, infer_schema_length=None).write_csv(out / "metrics.csv")
    print(f"evaluate: {len(rows)} variants from {Path(args.batch).name} -> {out / 'metrics.csv'}")
    return 0


def _selftest() -> int:
    df = pl.DataFrame({
        "patient_id": ["a", "b", "c", "d", "e"],
        "prescreened": [True, True, True, True, False],
        "sex": ["F", "M", "F", "M", "F"],
        "age": [70.0, 50.0, 80.0, 40.0, 60.0],
        "race_eth": ["white", "black", "white", "hispanic", "white"],
        "egfr": [30.0, 80.0, None, 50.0, 40.0],
        "egfr_days_ago": [10, 10, None, 400, 10],
        "tx": [False, False, False, True, False],
    })
    rules = {"criteria": [
        {"id": "I", "type": "inclusion", "computable": True, "field": "egfr", "operator": "between", "value": [25, 75], "lookback_days": 365},
        {"id": "E", "type": "exclusion", "computable": True, "field": "tx", "operator": "is_true"},
        {"id": "N", "type": "inclusion", "computable": False},
    ]}
    vs = [
        {"variant_id": "v0", "hash": "h0", "kind": "baseline", "label": "b", "params": {"I": [25, 75], "E": None}},
        {"variant_id": "v1", "hash": "h1", "kind": "loo", "label": "remove I", "params": {"E": None}},
        {"variant_id": "v2", "hash": "h2", "kind": "sweep", "label": "s", "params": {"I": [25, 90], "E": None}},
        {"variant_id": "v3", "hash": "h3", "kind": "loo", "label": "none", "params": {}},
    ]
    r = {x["variant_id"]: x for x in evaluate(vs, df, rules)}
    b = r["v0"]
    # a passes; b eGFR 80 > 75; c missing eGFR; d eGFR too old AND transplant
    assert b["n_prescreened"] == 4 and b["n_eligible"] == 1 and b["sf_proxy"] == 0.75
    assert b["fail_I"] == 3 and b["sole_I"] == 2 and b["fail_E"] == 1 and b["sole_E"] == 0
    assert b["gini_simpson"] is None and b["female"] == 1.0
    assert r["v1"]["n_eligible"] == 3 and r["v1"]["fail_I"] is None
    assert abs(r["v1"]["gini_simpson"] - (1 - (2 / 3) ** 2 - (1 / 3) ** 2)) < 1e-12
    assert r["v2"]["n_eligible"] == 2 and r["v3"]["n_eligible"] == 4
    with tempfile.TemporaryDirectory() as tmp:
        df.write_parquet(Path(tmp) / "f.parquet")
        (Path(tmp) / "b.json").write_text(json.dumps(vs))
        (Path(tmp) / "r.json").write_text(json.dumps(rules))
        run(argparse.Namespace(batch=Path(tmp) / "b.json", features=Path(tmp) / "f.parquet", rules=Path(tmp) / "r.json", out=Path(tmp) / "o"))
        assert pl.read_csv(Path(tmp) / "o" / "metrics.csv").height == 4
    print("evaluate selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("--batch", "--features", "--rules", "--out"):
        ap.add_argument(a)
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.batch and a.features and a.rules and a.out):
        ap.error("--batch, --features, --rules and --out are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
