"""Glue around the openadmet CLI for the trained-model folder.

The train map writes one slot per model: <trained>/<slot>/model/ is the
`openadmet anvil` output (cross_validation_metrics.json, anvil_recipe.yaml,
model.*). Slots are numbered, so the model label is read from the recipe.

  compare  run `openadmet compare` over every model's CV metrics
  predict  pick the best model by mean CV metric and run `openadmet predict`
  report   write metrics.csv (one row per model) and top_predictions.csv
"""

import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

TASK = "OPENADMET_LOGAC50"
PRED_COL = f"OADMET_PRED_openadmet-chembl_{TASK}"
METRICS = ["r2", "mae", "mse", "spearmanr", "ktau"]
LOWER_IS_BETTER = {"mae", "mse"}


def collect(trained):
    """[(label, model_dir, {metric: {mean, lower_ci, upper_ci}})] sorted by label."""
    rows = []
    for model_dir in sorted(Path(trained).glob("*/model")):
        recipe = yaml.safe_load((model_dir / "anvil_recipe.yaml").read_text())
        stats = json.loads((model_dir / "cross_validation_metrics.json").read_text())[TASK]
        rows.append((recipe["metadata"]["name"], model_dir, stats))
    if not rows:
        sys.exit(f"no trained models under {trained}")
    return sorted(rows, key=lambda r: r[0])


def best(rows, metric):
    sign = -1 if metric in LOWER_IS_BETTER else 1
    # NaN breaks max(): the pick would depend on row order.
    scored = [r for r in rows if not math.isnan(r[2][metric]["mean"])]
    if not scored:
        sys.exit(f"mean CV {metric} is NaN for every model")
    return max(scored, key=lambda r: sign * r[2][metric]["mean"])


def compare_args(rows, out_dir):
    args = ["openadmet", "compare"]
    for label, model_dir, _ in rows:
        args += ["--model-stats-fns", str(model_dir / "cross_validation_metrics.json"),
                 "--labels", label, "--task-names", TASK]
    return args + ["--output-dir", str(out_dir), "--report", "True"]


def predict_args(model_dir, compounds, out_csv):
    return ["openadmet", "predict", "--input-path", str(compounds),
            "--input-col", "OPENADMET_CANONICAL_SMILES", "--model-dir", str(model_dir),
            "--output-csv", str(out_csv), "--accelerator", "cpu"]  # v0.2.0 defaults to gpu


def check_compounds(path):
    with open(path, newline="") as f:
        header = next(csv.reader(f), [])
    if "OPENADMET_CANONICAL_SMILES" not in header:
        sys.exit(f"{path}: inference CSV needs an OPENADMET_CANONICAL_SMILES column; has {header}")


def metrics_rows(rows, metric):
    winner = best(rows, metric)[0]
    out = []
    for label, model_dir, stats in rows:
        row = {"model": label, "best": label == winner}
        for m in METRICS:
            row[f"{m}_mean"] = round(stats[m]["mean"], 4)
            row[f"{m}_lower_ci"] = round(stats[m]["lower_ci"], 4)
            row[f"{m}_upper_ci"] = round(stats[m]["upper_ci"], 4)
        row["n_folds"] = len(stats[metric]["value"])
        out.append(row)
    return out


def top_predictions(pred_csv, n):
    with open(pred_csv, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r[PRED_COL]]
    rows.sort(key=lambda r: float(r[PRED_COL]), reverse=True)
    return [{"rank": i + 1, "smiles": r["OPENADMET_CANONICAL_SMILES"],
             "inchikey": r.get("OPENADMET_INCHIKEY", ""),
             "predicted_pIC50": round(float(r[PRED_COL]), 3)} for i, r in enumerate(rows[:n])]


def write_csv(path, rows):
    if not rows:
        sys.exit(f"nothing to write to {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run(args):
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def selftest():
    """Unit test of the model collection, selection and CSV glue."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for slot, name, r2, mae in [("0", "lgbm", 0.45, 0.48), ("1", "rf", 0.51, 0.44)]:
            d = tmp / "trained" / slot / "model"
            d.mkdir(parents=True)
            (d / "anvil_recipe.yaml").write_text(yaml.safe_dump({"metadata": {"name": name}}))
            stats = {m: {"value": [v] * 4, "mean": v, "lower_ci": v - 0.1, "upper_ci": v + 0.1}
                     for m, v in [("r2", r2), ("mae", mae), ("mse", mae), ("spearmanr", r2), ("ktau", r2)]}
            (d / "cross_validation_metrics.json").write_text(json.dumps({"tag": "t", TASK: stats}))
        rows = collect(tmp / "trained")
        assert [r[0] for r in rows] == ["lgbm", "rf"]
        assert best(rows, "r2")[0] == "rf" and best(rows, "mae")[0] == "rf"
        nan_rf = [rows[0], (rows[1][0], rows[1][1], {"r2": {"mean": float("nan")}})]
        assert best(nan_rf, "r2")[0] == "lgbm" and best(nan_rf[::-1], "r2")[0] == "lgbm"
        a = compare_args(rows, tmp / "cmp")
        assert a.count("--model-stats-fns") == 2 and a[a.index("--labels") + 1] == "lgbm"
        assert a[-2:] == ["--report", "True"]
        p = predict_args(rows[1][1], "in.csv", "out.csv")
        assert p[p.index("--model-dir") + 1].endswith("1/model") and p[-2:] == ["--accelerator", "cpu"]
        m = metrics_rows(rows, "r2")
        assert [r["best"] for r in m] == [False, True] and m[0]["n_folds"] == 4
        src = tmp / "inf.csv"
        src.write_text("OPENADMET_CANONICAL_SMILES,OPENADMET_INCHIKEY\nC,A\n")
        check_compounds(src)
        (tmp / "bad.csv").write_text("smiles\nC\n")
        try:
            check_compounds(tmp / "bad.csv")
        except SystemExit:
            pass
        else:
            raise AssertionError("missing SMILES column accepted")
        pred = tmp / "pred.csv"
        pred.write_text(f"OPENADMET_CANONICAL_SMILES,OPENADMET_INCHIKEY,{PRED_COL}\nC,A,4.1\nCC,B,6.2\nCCC,C,\n")
        top = top_predictions(pred, 5)
        assert [t["smiles"] for t in top] == ["CC", "C"] and top[0]["rank"] == 1
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["compare", "predict", "report"], nargs="?")
    ap.add_argument("--selftest", action="store_true", help="run the unit test and exit")
    ap.add_argument("--trained", type=Path)
    ap.add_argument("--out", type=Path, help="compare: output dir; predict: predictions CSV; report: metrics CSV")
    ap.add_argument("--top-out", type=Path, help="report: top predictions CSV")
    ap.add_argument("--compounds", type=Path, help="predict: inference CSV")
    ap.add_argument("--predictions", type=Path, help="report: predictions CSV")
    ap.add_argument("--metric", default="r2", choices=METRICS)
    ap.add_argument("--top", type=int, default=50)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.mode and a.trained and a.out):
        ap.error("mode, --trained and --out are required")
    if a.mode == "predict" and not a.compounds:
        ap.error("predict needs --compounds")
    if a.mode == "report" and not (a.predictions and a.top_out):
        ap.error("report needs --predictions and --top-out")
    rows = collect(a.trained)
    if a.mode == "compare":
        a.out.mkdir(parents=True, exist_ok=True)  # openadmet compare needs it to exist
        run(compare_args(rows, a.out))
    elif a.mode == "predict":
        check_compounds(a.compounds)
        label, model_dir, stats = best(rows, a.metric)
        print(f"best model by mean CV {a.metric}: {label} ({stats[a.metric]['mean']:.3f})")
        a.out.parent.mkdir(parents=True, exist_ok=True)
        run(predict_args(model_dir, a.compounds, a.out))
    else:
        write_csv(a.out, metrics_rows(rows, a.metric))
        write_csv(a.top_out, top_predictions(a.predictions, a.top))
        print(f"wrote {a.out} and {a.top_out}")


if __name__ == "__main__":
    sys.exit(main())
