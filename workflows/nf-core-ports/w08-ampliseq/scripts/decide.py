#!/usr/bin/env python3
"""
The Groovy fan-outs of nf-core/ampliseq's QIIME2 statistics, as item folders.

The pipeline combines channels to run one task per metadata column, distance
matrix, formula and taxonomic level (subworkflows qiime2_diversity and
qiime2_ancom). Here each combination is one bash-sourceable file in a folder;
a ``horus_map`` over that folder runs one slot per file.

Inputs are the stdout of METADATA_ALL and METADATA_PAIRWISE (comma separated
column names, maybe empty) and the parameter values. The diversity metric
names are the fixed outputs of ``qiime diversity core-metrics-phylogenetic``.

Writes one folder per list (``--out <list>=<folder>``):

- ``ancom/<col>``: QIIME2_FILTERSAMPLES_ANCOM, QIIME2_ANCOMBC_ASV, QIIME2_ANCOMBC2_ASV
- ``ancom_tax/<col>-<level>``: QIIME2_ANCOMBC_TAX, QIIME2_ANCOMBC2_TAX
- ``formula/<i>``, ``formula_tax/<i>-<level>``: ANCOMBC_FORMULA_ASV / _TAX
- ``formula2/<i>``, ``formula2_tax/<i>-<level>``: ANCOMBC2_FORMULA_ASV / _TAX
- ``alpha/<vector>``, ``betaord/<pcoa>``: QIIME2_DIVERSITY_ALPHA / _BETAORD
- ``beta/<matrix>-<col>``: QIIME2_DIVERSITY_BETA (pairwise columns)
- ``adonis/<matrix>-<i>``: QIIME2_DIVERSITY_ADONIS (one per formula term)

stdlib only.

Usage:
    decide.py --all all.txt --pairwise pairwise.txt --adonis-formula F --ancombc-formula F \\
        --ancombc2-formula F --tax-agglom-min 2 --tax-agglom-max 2 --out ancom=DIR ...
    decide.py --selftest
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

VECTORS = ["evenness_vector", "faith_pd_vector", "observed_features_vector", "shannon_vector"]
METRICS = ["bray_curtis", "jaccard", "unweighted_unifrac", "weighted_unifrac"]


def tokens(text: str) -> list[str]:
    """splitCsv().flatten() of a stdout line, or Groovy tokenize(',')."""
    return [t for t in (x.strip() for x in text.strip().split(",")) if t]


def items(a: argparse.Namespace) -> dict[str, dict[str, dict[str, str]]]:
    cols = tokens(a.all.read_text())
    pairwise = tokens(a.pairwise.read_text())
    levels = range(a.tax_agglom_min, a.tax_agglom_max + 1)
    f1 = tokens(a.ancombc_formula.replace(" ", ""))
    f2 = tokens(a.ancombc2_formula.replace(" ", ""))
    out: dict[str, dict[str, dict[str, str]]] = {
        "ancom": {c: {"col": c} for c in cols},
        "ancom_tax": {f"{c}-{lv}": {"col": c, "level": str(lv)} for c in cols for lv in levels},
        "formula": {str(i): {"formula": f} for i, f in enumerate(f1)},
        "formula_tax": {f"{i}-{lv}": {"formula": f, "level": str(lv)} for i, f in enumerate(f1) for lv in levels},
        "formula2": {str(i): {"formula": f} for i, f in enumerate(f2)},
        "formula2_tax": {f"{i}-{lv}": {"formula": f, "level": str(lv)} for i, f in enumerate(f2) for lv in levels},
        "alpha": {v: {"name": v} for v in VECTORS},
        "betaord": {f"{m}_pcoa_results": {"name": f"{m}_pcoa_results"} for m in METRICS},
        "beta": {f"{m}-{c}": {"matrix": f"{m}_distance_matrix", "col": c} for m in METRICS for c in pairwise},
        "adonis": {
            f"{m}-{i}": {"matrix": f"{m}_distance_matrix", "formula": f}
            for m in METRICS
            for i, f in enumerate(tokens(a.adonis_formula))
        },
    }
    return out


def write(outs: dict[str, Path], lists: dict[str, dict[str, dict[str, str]]]) -> None:
    for name, entries in lists.items():
        d = outs[name]
        d.mkdir(parents=True, exist_ok=True)
        for key, meta in entries.items():
            # values are metadata column names and formulas: single-quote them for sh
            (d / key).write_text("".join(f"{k}='{v}'\n" for k, v in meta.items()))


def selftest() -> None:
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "all.txt").write_text("treatment1,mix8,badpairwise10")
        (Path(t) / "pw.txt").write_text("treatment1,mix8")
        a = argparse.Namespace(
            all=Path(t) / "all.txt", pairwise=Path(t) / "pw.txt", adonis_formula="treatment1,mix8",
            ancombc_formula="treatment1", ancombc2_formula="treatment1", tax_agglom_min=2, tax_agglom_max=2,
        )
        got = items(a)
        # the counts the test profile runs (trace.txt)
        assert [len(got[k]) for k in ("ancom", "ancom_tax", "alpha", "betaord", "beta", "adonis", "formula", "formula_tax")] == [3, 3, 4, 4, 8, 8, 1, 1]
        write({k: Path(t) / "lists" / k for k in got}, got)
        assert (Path(t) / "lists/beta/jaccard-mix8").read_text() == "matrix='jaccard_distance_matrix'\ncol='mix8'\n"
        (Path(t) / "all.txt").write_text("")
        assert items(a)["ancom"] == {}
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", type=Path, required=True)
    ap.add_argument("--pairwise", type=Path, required=True)
    ap.add_argument("--adonis-formula", default="")
    ap.add_argument("--ancombc-formula", default="")
    ap.add_argument("--ancombc2-formula", default="")
    ap.add_argument("--tax-agglom-min", type=int, default=2)
    ap.add_argument("--tax-agglom-max", type=int, default=6)
    ap.add_argument("--out", action="append", required=True, help="<list>=<folder>, one per list")
    a = ap.parse_args()
    outs = {k: Path(v) for k, v in (o.split("=", 1) for o in a.out)}
    lists = items(a)
    if set(outs) != set(lists):
        raise SystemExit(f"--out needs exactly {sorted(lists)}")
    write(outs, lists)


if __name__ == "__main__":
    main()
