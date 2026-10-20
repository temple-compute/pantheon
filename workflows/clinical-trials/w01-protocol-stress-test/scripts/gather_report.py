#!/usr/bin/env python3
"""Gather every evaluated batch and write the stress-test report.

Per criterion (computable ones, from the baseline and leave-one-out rows):
  sole_cause        prescreened patients who fail only this criterion at baseline
  delta_eligible    eligible patients gained when the criterion is removed
  delta_sf_proxy    change in screen-failure proxy when it is removed
  delta_diversity   change in Gini-Simpson race/ethnicity diversity when removed
Threshold curves: one-at-a-time sweep points (all other criteria at baseline).
Pareto frontier: variants not dominated on (n_eligible, gini_simpson).

Outputs: summary.json (deterministic for a given seed), provenance.json,
variants.csv (every variant), report.html (self-contained) and hero.png
(1200x630).

Usage:
    python gather_report.py --evaluated evaluated/ --prescreen prescreen.json \
        --rules criteria.json --diff criteria_diff.json --protocol NCT.json --config config.json \
        --summary summary.json --provenance provenance.json --variants variants.csv \
        --report report.html --hero hero.png
    python gather_report.py --selftest
"""

import argparse
import base64
import hashlib
import html
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import polars as pl

GOLD, INK, MUTED, RULE = "#B97C3B", "#1F1A17", "#6B625C", "#E8E2DC"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_metrics(evaluated: Path) -> pl.DataFrame:
    files = sorted(evaluated.glob("*/metrics.csv"))
    if not files:
        raise SystemExit(f"gather_report: no */metrics.csv under {evaluated}")
    df = pl.concat([pl.read_csv(f, infer_schema_length=0) for f in files], how="diagonal")
    # Read as text and cast once: an all-empty column in one batch would otherwise infer as String.
    text = {"variant_id", "hash", "kind", "label", "params"}
    ints = [c for c in df.columns if c.startswith(("n_", "fail_", "sole_"))]
    return df.with_columns(
        [pl.col(c).cast(pl.Int64) for c in ints]
        + [pl.col(c).cast(pl.Float64) for c in df.columns if c not in text and c not in ints]
    ).sort("variant_id")


def pareto(df: pl.DataFrame) -> pl.DataFrame:
    """Variants no other variant beats on both n_eligible and gini_simpson."""
    pts = df.filter(pl.col("gini_simpson").is_not_null()).sort(["n_eligible", "gini_simpson", "variant_id"], descending=[True, True, False])
    keep, best = [], -1.0
    for row in pts.iter_rows(named=True):
        if row["gini_simpson"] > best:
            keep.append(row["variant_id"])
            best = row["gini_simpson"]
    return df.filter(pl.col("variant_id").is_in(keep)).sort("n_eligible", descending=True)


def analyse(df: pl.DataFrame, rules: dict) -> dict:
    base = df.filter(pl.col("kind") == "baseline").row(0, named=True)
    crit = [c for c in rules["criteria"] if c.get("computable")]
    base_params = json.loads(base["params"])
    per = []
    for c in crit:
        loo = df.filter((pl.col("kind") == "loo") & (pl.col("label") == f"remove {c['id']}"))
        loo = loo.row(0, named=True) if loo.height else base  # dropped as a duplicate of baseline
        gs0, gs1 = base["gini_simpson"], loo["gini_simpson"]
        per.append({
            "id": c["id"], "short": c.get("short", c["id"]), "type": c["type"], "text": c["text"], "reason": c.get("reason", ""),
            "fail": base[f"fail_{c['id']}"], "sole_cause": base[f"sole_{c['id']}"],
            "n_eligible_removed": loo["n_eligible"],
            "delta_eligible": loo["n_eligible"] - base["n_eligible"],
            "delta_sf_proxy": round(loo["sf_proxy"] - base["sf_proxy"], 6),
            "delta_diversity": round(gs1 - gs0, 6) if gs0 is not None and gs1 is not None else None,
        })
    per.sort(key=lambda r: (-r["delta_eligible"], -r["sole_cause"], r["id"]))
    curves = {}
    for c in crit:
        if not c.get("sweep"):
            continue
        pts = []
        for row in df.filter(pl.col("kind").is_in(["baseline", "sweep"])).iter_rows(named=True):
            p = json.loads(row["params"])
            if all(p.get(k) == v for k, v in base_params.items() if k != c["id"]) and set(p) == set(base_params):
                pts.append({"value": p[c["id"]], "n_eligible": row["n_eligible"], "sf_proxy": round(row["sf_proxy"], 6), "gini_simpson": row["gini_simpson"]})
        curves[c["id"]] = sorted(pts, key=lambda x: json.dumps(x["value"]))
    front = pareto(df)
    top = front.head(10).select(["variant_id", "hash", "kind", "label", "n_eligible", "sf_proxy", "gini_simpson", "female", "age_ge_65"]).to_dicts()
    lead = per[0]
    best_sweep = df.filter(pl.col("kind") == "sweep").sort(["n_eligible", "variant_id"], descending=[True, False]).row(0, named=True)
    return {
        "baseline": {k: base[k] for k in ("variant_id", "hash", "n_prescreened", "n_eligible", "eligible_share", "sf_proxy", "gini_simpson", "female", "age_ge_65", "age_ge_75")},
        "n_variants": df.height,
        "variants_by_kind": dict(sorted(df["kind"].value_counts().iter_rows())),
        "headline": {
            "criterion": lead["id"], "short": lead["short"], "text": lead["text"],
            "baseline_eligible": base["n_eligible"], "removed_eligible": lead["n_eligible_removed"],
            "baseline_sf_proxy": round(base["sf_proxy"], 6), "removed_sf_proxy": round(base["sf_proxy"] + lead["delta_sf_proxy"], 6),
            "sole_cause": lead["sole_cause"],
        },
        "best_sweep_variant": {k: best_sweep[k] for k in ("variant_id", "hash", "label", "n_eligible", "sf_proxy", "gini_simpson")},
        "criteria": per,
        "non_computable": [{"id": c["id"], "short": c.get("short", c["id"]), "type": c["type"], "text": c["text"], "reason": c.get("reason", "")} for c in rules["criteria"] if not c.get("computable")],
        "threshold_curves": curves,
        "pareto_size": front.height,
        "pareto_top": top,
    }


def headline_text(s: dict) -> str:
    h = s["headline"]
    return (f"Removing {h['criterion']} ({h['short']}) lifts the eligible pool from {h['baseline_eligible']} to {h['removed_eligible']} "
            f"of {s['baseline']['n_prescreened']} prescreened patients; the screen-failure proxy falls from "
            f"{h['baseline_sf_proxy']:.1%} to {h['removed_sf_proxy']:.1%}.")


def hero(s: dict, nct: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import font_manager
    import matplotlib.pyplot as plt

    names = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = "Inter" if "Inter" in names else "DejaVu Sans"
    rows = [r for r in s["criteria"] if r["delta_eligible"] > 0][:8][::-1]
    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor="white")
    ax = fig.add_axes([0.26, 0.14, 0.68, 0.58])
    labels = [f"{r['id']} · {r['short']}" for r in rows]
    vals = [r["delta_eligible"] for r in rows]
    ax.barh(labels, vals, color=GOLD, height=0.62)
    for y, v in enumerate(vals):
        ax.text(v, y, f"  +{v}", va="center", fontsize=12, color=INK)
    ax.set_xlim(0, max(vals + [1]) * 1.15)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.tick_params(axis="y", length=0, labelsize=12, labelcolor=INK)
    ax.tick_params(axis="x", colors=MUTED, labelsize=10)
    ax.set_xlabel("Eligible patients gained when the criterion is removed", color=MUTED, fontsize=11)
    h = s["headline"]
    best = s["best_sweep_variant"]
    fig.text(0.04, 0.9, f"Removing {h['criterion']} ({h['short']}): {h['baseline_eligible']} → {h['removed_eligible']} eligible patients",
             fontsize=22, fontweight="bold", color=INK)
    fig.text(0.04, 0.83, f"Screen-failure proxy {h['baseline_sf_proxy']:.1%} → {h['removed_sf_proxy']:.1%} across "
             f"{s['baseline']['n_prescreened']} prescreened synthetic CKD patients · {s['n_variants']} protocol variants",
             fontsize=13, color=MUTED)
    fig.text(0.04, 0.78, f"Best relaxed variant ({best['label']}): {best['n_eligible']} eligible, screen-failure proxy {best['sf_proxy']:.1%}",
             fontsize=13, color=GOLD)
    fig.text(0.04, 0.04, f"{nct} eligibility on a Synthea population. Synthetic data; not clinical evidence.", fontsize=10, color=MUTED)
    fig.text(0.96, 0.04, "Temple Compute · Horus", fontsize=11, color=GOLD, ha="right", fontweight="bold")
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)


def _fmt(v, pct=False):
    if v is None:
        return "–"
    if pct:
        return f"{v:.1%}"
    return f"{v:.3f}" if isinstance(v, float) else html.escape(str(v))


def report_html(s: dict, prov: dict, pre: dict, diff: dict, hero_png: Path) -> str:
    img = base64.b64encode(hero_png.read_bytes()).decode()
    crit_rows = "".join(
        f"<tr><td>{r['id']}</td><td>{r['type']}</td><td><b>{html.escape(r['short'])}</b><br><span class=m>{html.escape(r['text'])}</span></td><td class=n>{r['fail']}</td>"
        f"<td class=n>{r['sole_cause']}</td><td class=n>+{r['delta_eligible']}</td><td class=n>{r['delta_sf_proxy']:+.1%}</td>"
        f"<td class=n>{_fmt(r['delta_diversity'])}</td><td class=m>{html.escape(r['reason'])}</td></tr>" for r in s["criteria"])
    nc_rows = "".join(f"<tr><td>{r['id']}</td><td>{html.escape(r['text'])}</td><td class=m>{html.escape(r['reason'])}</td></tr>" for r in s["non_computable"])
    curve_html = "".join(
        f"<h3>{cid}</h3><table><tr><th>value</th><th>eligible</th><th>SF proxy</th><th>diversity</th></tr>"
        + "".join(f"<tr><td>{html.escape(json.dumps(p['value']))}</td><td class=n>{p['n_eligible']}</td><td class=n>{_fmt(p['sf_proxy'], True)}</td><td class=n>{_fmt(p['gini_simpson'])}</td></tr>" for p in pts)
        + "</table>" for cid, pts in s["threshold_curves"].items())
    top_rows = "".join(
        f"<tr><td>{r['variant_id']}</td><td><code>{r['hash']}</code></td><td>{r['kind']}</td><td>{html.escape(r['label'])}</td>"
        f"<td class=n>{r['n_eligible']}</td><td class=n>{_fmt(r['sf_proxy'], True)}</td><td class=n>{_fmt(r['gini_simpson'])}</td></tr>" for r in s["pareto_top"])
    cov = "".join(f"<tr><td>{k}</td><td class=n>{v}</td></tr>" for k, v in pre["prescreened_coverage"].items())
    if diff.get("status") == "ok":
        llm = f"<p>{diff['n_agree']} of {diff['n_reviewed']} reviewed rules match the {html.escape(diff['model'])} draft exactly on type, field, operator, value, lookback and computability.</p><ul>" + "".join(
            f"<li><b>{r['id']}</b>: {html.escape('; '.join(r['differences']))}</li>" for r in diff["criteria"] if not r["agrees"]) + "</ul>"
    else:
        llm = f"<p>{html.escape(diff.get('message', 'not run'))}</p>"
    b = s["baseline"]
    comp = pre["prescreened_composition"]
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Protocol Stress-Test</title><style>
body{{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:{INK};background:#fff;max-width:1100px;margin:0 auto;padding:24px 16px;line-height:1.5}}
h1{{font-size:28px;margin:0 0 4px}} h2{{border-bottom:2px solid {GOLD};padding-bottom:4px;margin-top:36px}} h3{{margin:18px 0 6px}}
.lead{{font-size:19px;background:#FBF6F0;border-left:4px solid {GOLD};padding:12px 16px}} .m{{color:{MUTED};font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}} td,th{{border-bottom:1px solid {RULE};padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#FBF6F0}} .n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}} img{{max-width:100%;height:auto}}
.wrap{{overflow-x:auto}} code{{font-size:12px}}</style></head><body>
<h1>Protocol Stress-Test: {html.escape(prov['nct_id'])}</h1>
<p class=m>{html.escape(prov['brief_title'])}. Lead sponsor (per ClinicalTrials.gov): {html.escape(prov['lead_sponsor'])}. Synthetic population; screen failure is a proxy; not clinical evidence.</p>
<p class=lead>{html.escape(headline_text(s))}</p>
<img src="data:image/png;base64,{img}" alt="Eligible patients gained per removed criterion">
<h2>Baseline</h2><table>
<tr><td>Patients alive at index ({pre['index_date']})</td><td class=n>{pre['n_alive_at_index']}</td></tr>
<tr><td>Prescreened (active CKD diagnosis, age ≥18)</td><td class=n>{b['n_prescreened']}</td></tr>
<tr><td>Eligible under the full computable protocol</td><td class=n>{b['n_eligible']}</td></tr>
<tr><td>Screen-failure proxy (1 − eligible / prescreened)</td><td class=n>{_fmt(b['sf_proxy'], True)}</td></tr>
<tr><td>Prescreened: female / age ≥65 / age ≥75</td><td class=n>{_fmt(comp['female'], True)} / {_fmt(comp['age_ge_65'], True)} / {_fmt(comp['age_ge_75'], True)}</td></tr>
<tr><td>Variants evaluated</td><td class=n>{s['n_variants']}</td></tr></table>
<h2>What each criterion costs</h2><p class=m>Sole cause: prescreened patients who fail only this criterion. Δ columns compare removing the criterion with the baseline. Diversity is the Gini-Simpson index over race/ethnicity groups (1 − Σp²).</p>
<div class=wrap><table><tr><th>ID</th><th>Type</th><th>Criterion</th><th>Fail</th><th>Sole cause</th><th>Δ eligible</th><th>Δ SF proxy</th><th>Δ diversity</th><th>Implementation</th></tr>{crit_rows}</table></div>
<h2>Not simulated</h2><table><tr><th>ID</th><th>Criterion</th><th>Why</th></tr>{nc_rows}</table>
<h2>Threshold sweeps (one criterion at a time)</h2>{curve_html}
<h2>Pareto frontier: pool size vs diversity</h2><p class=m>{s['pareto_size']} non-dominated variants; top 10 by pool size.</p>
<div class=wrap><table><tr><th>Variant</th><th>Hash</th><th>Kind</th><th>Change</th><th>Eligible</th><th>SF proxy</th><th>Diversity</th></tr>{top_rows}</table></div>
<h2>LLM draft vs reviewed rules</h2>{llm}
<h2>Data coverage among prescreened patients</h2><p class=m>Non-null values per measured feature; patients flagged for boolean features.</p><table>{cov}</table>
<h2>Provenance</h2><pre>{html.escape(json.dumps(prov, indent=2))}</pre>
</body></html>"""


def provenance(args, pre: dict, protocol: dict, cfg: dict) -> dict:
    ps = protocol["protocolSection"]
    pkgs = {}
    for p in ("polars", "numpy", "matplotlib", "pyarrow", "jdk4py", "anthropic"):
        try:
            pkgs[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pass
    gen = [sh for sh in pre["shards"] if sh.get("mode") == "generate"]
    return {
        "nct_id": ps["identificationModule"]["nctId"],
        "brief_title": ps["identificationModule"]["briefTitle"],
        "lead_sponsor": ps["sponsorCollaboratorsModule"]["leadSponsor"]["name"],
        "protocol_snapshot_sha256": sha256(args.protocol),
        "protocol_last_update": ps["statusModule"].get("lastUpdatePostDateStruct", {}).get("date"),
        "criteria_file_sha256": sha256(args.rules),
        "config_sha256": sha256(args.config),
        "index_date": cfg["index_date"],
        "population_source": "synthea" if gen else "import",
        "synthea_version": gen[0]["synthea_version"] if gen else None,
        "synthea_jar_sha256": gen[0]["jar_sha256"] if gen else None,
        "synthea_seeds": [sh["seed"] for sh in gen],
        "synthea_state": gen[0]["state"] if gen else None,
        "population_requested": cfg["population"]["size"],
        "patients_generated": pre["n_patients_generated"],
        "patients_alive_at_index": pre["n_alive_at_index"],
        "imported_from": [sh["source"] for sh in pre["shards"] if sh.get("mode") == "import"],
        "packages": pkgs,
        "python": platform.python_version(),
        # The horus CLI exposes no run id to tasks; the task's cwd is its execution directory.
        "horus_execution_dir": Path.cwd().name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def run(args) -> int:
    df = load_metrics(Path(args.evaluated))
    rules = json.loads(Path(args.rules).read_text())
    pre = json.loads(Path(args.prescreen).read_text())
    protocol = json.loads(Path(args.protocol).read_text())
    cfg = json.loads(Path(args.config).read_text())
    diff = json.loads(Path(args.diff).read_text())
    s = analyse(df, rules)
    s["headline_text"] = headline_text(s)
    s["prescreen"] = {k: pre[k] for k in ("index_date", "n_alive_at_index", "n_prescreened", "prescreened_composition")}
    s["llm_diff"] = {k: diff.get(k) for k in ("status", "model", "n_agree", "n_reviewed")}
    prov = provenance(args, pre, protocol, cfg)
    for p in (args.summary, args.provenance, args.variants, args.report, args.hero):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
    Path(args.provenance).write_text(json.dumps(prov, indent=2) + "\n")
    df.write_csv(args.variants)
    hero(s, prov["nct_id"], Path(args.hero))
    Path(args.report).write_text(report_html(s, prov, pre, diff, Path(args.hero)))
    print(f"gather_report: {s['headline_text']}")
    return 0


def _selftest() -> int:
    rules = {"criteria": [
        {"id": "A", "short": "Lab", "type": "inclusion", "text": "lab in range", "computable": True, "operator": "between", "value": [1, 2], "sweep": {"low": [0, 1], "high": [2]}},
        {"id": "B", "type": "exclusion", "text": "event", "computable": True, "operator": "is_true"},
        {"id": "C", "type": "inclusion", "text": "consent", "computable": False, "reason": "procedural"},
    ]}
    def row(vid, kind, label, n, gs, params, fa, sa, fb, sb):
        return {"variant_id": vid, "hash": vid, "kind": kind, "label": label, "n_prescreened": 10, "n_eligible": n,
                "eligible_share": n / 10, "sf_proxy": 1 - n / 10, "female": 0.5, "age_ge_65": 0.5, "age_ge_75": 0.1,
                "gini_simpson": gs, "fail_A": fa, "sole_A": sa, "fail_B": fb, "sole_B": sb, "params": json.dumps(params, sort_keys=True)}
    rows = [
        row("v0", "baseline", "baseline", 2, 0.5, {"A": [1, 2], "B": None}, 6, 4, 3, 1),
        row("v1", "loo", "remove A", 6, 0.4, {"B": None}, None, None, 3, 3),
        row("v2", "loo", "remove B", 3, 0.6, {"A": [1, 2]}, 6, 6, None, None),
        row("v3", "sweep", "A=[0,2]", 4, 0.55, {"A": [0, 2], "B": None}, 4, 2, 3, 1),
    ]
    df = pl.DataFrame(rows)
    s = analyse(df, rules)
    assert [r["id"] for r in s["criteria"]] == ["A", "B"]
    assert s["criteria"][0]["delta_eligible"] == 4 and s["criteria"][0]["sole_cause"] == 4
    assert abs(s["criteria"][0]["delta_sf_proxy"] + 0.4) < 1e-9 and abs(s["criteria"][1]["delta_diversity"] - 0.1) < 1e-9
    assert [p["value"] for p in s["threshold_curves"]["A"]] == [[0, 2], [1, 2]]
    assert [r["variant_id"] for r in s["pareto_top"]] == ["v1", "v3", "v2"]  # v0 is dominated by v3
    assert s["non_computable"][0]["id"] == "C" and s["headline"]["criterion"] == "A"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "ev" / "0").mkdir(parents=True)
        df.write_csv(t / "ev" / "0" / "metrics.csv")
        (t / "rules.json").write_text(json.dumps(rules))
        (t / "pre.json").write_text(json.dumps({"index_date": "2026-01-01", "n_patients_generated": 12, "n_alive_at_index": 11, "n_prescreened": 10,
                                                "prescreened_composition": {"female": 0.5, "age_ge_65": 0.5, "age_ge_75": 0.1}, "prescreened_coverage": {"x": 1},
                                                "shards": [{"mode": "generate", "synthea_version": "v4.0.0", "jar_sha256": "x", "seed": 1, "state": "Utah"}]}))
        (t / "proto.json").write_text(json.dumps({"protocolSection": {"identificationModule": {"nctId": "NCT0", "briefTitle": "T"},
                                                                      "sponsorCollaboratorsModule": {"leadSponsor": {"name": "S"}}, "statusModule": {}}}))
        (t / "cfg.json").write_text(json.dumps({"index_date": "2026-01-01", "population": {"size": 12}}))
        (t / "diff.json").write_text(json.dumps({"status": "skipped", "message": "no key"}))
        a = argparse.Namespace(evaluated=t / "ev", prescreen=t / "pre.json", rules=t / "rules.json", diff=t / "diff.json", protocol=t / "proto.json",
                               config=t / "cfg.json", summary=t / "o/s.json", provenance=t / "o/p.json", variants=t / "o/v.csv", report=t / "o/r.html", hero=t / "o/h.png")
        run(a)
        from struct import unpack
        assert unpack(">II", (t / "o/h.png").read_bytes()[16:24]) == (1200, 630)
        assert "Removing A (Lab)" in (t / "o/r.html").read_text() and "—" not in (t / "o/r.html").read_text()
    print("gather_report selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("--evaluated", "--prescreen", "--rules", "--diff", "--protocol", "--config", "--summary", "--provenance", "--variants", "--report", "--hero"):
        ap.add_argument(a)
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    missing = [k for k, v in vars(a).items() if v is None and k != "selftest"]
    if missing:
        ap.error("missing: " + ", ".join("--" + m for m in missing))
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
