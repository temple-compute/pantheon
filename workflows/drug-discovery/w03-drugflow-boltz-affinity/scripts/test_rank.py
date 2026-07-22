"""Tests for the pure ΔG helpers in rank.py.

Ported from the legacy boltz-drugflow plugin's
``tests/backend/test_boltz_affinity.py`` (driver pure-helper cases only).
"""

from pathlib import Path

import pytest
from rank import (
    CSV_COLUMNS,
    affinity_to_deltaG,
    build_row,
    parse_affinity_json,
    write_table,
)


def test_affinity_to_delta_g_known_value() -> None:
    """ΔG ≈ 1.364 * (pred_value - 6); pred_value 6 -> 0 kcal/mol."""
    assert affinity_to_deltaG(6.0) == 0.0
    # pred_value 0 (IC50 ~1 µM) -> 1.364 * (-6) = -8.184
    assert affinity_to_deltaG(0.0) == pytest.approx(-8.184, abs=1e-3)


def test_parse_affinity_json_prefers_binary_probability() -> None:
    """Parsing extracts the pred value and the binary probability key."""
    parsed = parse_affinity_json(
        {
            "affinity_pred_value": 1.5,
            "affinity_probability_binary": 0.9,
        }
    )
    assert parsed == {
        "affinity_pred_value": 1.5,
        "binding_probability": 0.9,
    }


def test_parse_affinity_json_falls_back_to_probability() -> None:
    """When the binary key is absent, the generic probability is used."""
    parsed = parse_affinity_json(
        {"affinity_pred_value": 2.0, "affinity_probability": 0.7}
    )
    assert parsed == {
        "affinity_pred_value": 2.0,
        "binding_probability": 0.7,
    }


def test_build_row_computes_delta_g() -> None:
    """build_row merges metadata + affinity and computes ΔG."""
    row = build_row(
        "mol_1",
        "CCO",
        {"affinity_pred_value": 6.0, "binding_probability": 0.5},
    )
    assert row == {
        "molecule": "mol_1",
        "smiles": "CCO",
        "affinity_pred_value": 6.0,
        "binding_probability": 0.5,
        "deltaG_kcal_per_mol": 0.0,
    }


def test_write_table_sorts_by_delta_g(tmp_path: Path) -> None:
    """The CSV has the expected header and is sorted by ascending ΔG."""
    rows = [
        build_row("weak", "C", {"affinity_pred_value": 8.0}),
        build_row("strong", "CC", {"affinity_pred_value": 2.0}),
    ]
    csv_path = tmp_path / "table.csv"
    write_table(rows, str(csv_path))

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    # strong (lower ΔG) comes first
    assert lines[1].startswith("strong")
    assert lines[2].startswith("weak")
