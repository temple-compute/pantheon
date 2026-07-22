"""Turn Boltz-2 affinity outputs into a ranked ΔG table.

Walks the gathered predictions folder, parses every ``affinity_*.json`` Boltz
produced, converts the predicted affinity into an approximate binding free
energy and writes a CSV sorted by ΔG (best first).

Stdlib-only on purpose: this stage runs under a bare ``python3`` on the target.
"""

from __future__ import annotations

import argparse
from typing import Any

# --- Pure, stdlib-only helpers (unit-tested) -----------------------------

# 2.303 * R * T at 298.15 K, in kcal/mol (ΔG = 2.303·R·T·log10(K)).
_RT_LN10_KCAL = 1.364

# Boltz-2 reports ``affinity_pred_value`` as ~log10(IC50) with IC50 in µM.
# Converting to molar and treating IC50 as a Kd proxy:
#   log10(IC50 [M]) = affinity_pred_value - 6
_UM_TO_M_LOG10 = 6

CSV_COLUMNS = [
    "molecule",
    "smiles",
    "affinity_pred_value",
    "binding_probability",
    "deltaG_kcal_per_mol",
]


def affinity_to_deltaG(pred_value: float) -> float:  # noqa: N802
    """Approximate binding ΔG (kcal/mol) from Boltz's affinity value.

    Boltz-2 ``affinity_pred_value`` is ~log10(IC50) with IC50 in µM. Treating
    IC50 as a Kd proxy at 298 K::

        ΔG ≈ 1.364 * (affinity_pred_value - 6)

    This is an approximation (IC50 ≈ Kd, standard conditions), useful for
    ranking rather than as an exact free energy.
    """
    return round(_RT_LN10_KCAL * (float(pred_value) - _UM_TO_M_LOG10), 4)


def parse_affinity_json(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the affinity value and binding probability from Boltz output.

    Accepts the parsed ``affinity_*.json`` dict and tolerates the alternative
    probability key names Boltz has used across versions.
    """
    pred_value = data.get("affinity_pred_value")
    probability = data.get(
        "affinity_probability_binary",
        data.get("affinity_probability", None),
    )
    return {
        "affinity_pred_value": pred_value,
        "binding_probability": probability,
    }


def build_row(
    molecule: str, smiles: str, affinity: dict[str, Any]
) -> dict[str, Any]:
    """Combine molecule metadata and a parsed affinity dict into a CSV row."""
    pred_value = affinity.get("affinity_pred_value")
    delta_g = (
        affinity_to_deltaG(pred_value) if pred_value is not None else None
    )
    return {
        "molecule": molecule,
        "smiles": smiles,
        "affinity_pred_value": pred_value,
        "binding_probability": affinity.get("binding_probability"),
        "deltaG_kcal_per_mol": delta_g,
    }


def write_table(rows: list[dict[str, Any]], csv_path: str) -> None:
    """Write ΔG rows to *csv_path* as CSV (sorted by ΔG, ascending)."""
    import csv

    def _sort_key(row: dict[str, Any]) -> float:
        value = row.get("deltaG_kcal_per_mol")
        return float("inf") if value is None else value

    ordered = sorted(rows, key=_sort_key)
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in ordered:
            writer.writerow(row)


def collect_affinity_rows(
    out_dir: str, smiles_by_name: dict[str, str]
) -> list[dict[str, Any]]:
    """Walk Boltz's output tree and build ΔG rows for each prediction."""
    import glob
    import json
    import os

    rows = []
    pattern = os.path.join(out_dir, "**", "affinity_*.json")
    for json_path in sorted(glob.glob(pattern, recursive=True)):
        name = os.path.basename(json_path)[len("affinity_") : -len(".json")]
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        affinity = parse_affinity_json(data)
        rows.append(build_row(name, smiles_by_name.get(name, ""), affinity))
    if not rows:
        raise RuntimeError(
            f"Boltz finished but no affinity outputs were found in {out_dir}."
        )
    return rows


# --- glue ----------------------------------------------------------------


def main() -> None:
    import json

    parser = argparse.ArgumentParser(description="Boltz-2 ΔG table builder")
    parser.add_argument(
        "--predictions", required=True, help="Gathered Boltz predictions dir."
    )
    parser.add_argument(
        "--smiles", required=True, help="{name: smiles} JSON map."
    )
    parser.add_argument("--out", required=True, help="Output CSV path.")
    args = parser.parse_args()

    with open(args.smiles, encoding="utf-8") as fh:
        smiles_by_name = json.load(fh)

    rows = collect_affinity_rows(args.predictions, smiles_by_name)
    write_table(rows, args.out)
    print(f"Wrote ΔG table with {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
