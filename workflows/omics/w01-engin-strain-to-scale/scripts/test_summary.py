"""Tests for the pure merge helpers in summary.py, against the captured
example outputs in examples/expected-output/ (deterministic under seed: 0).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # summary.py sits next to this file

import pytest
from summary import intervals_overlap, summarize_host, summarize_pathway, summarize_process

EXPECTED = Path(__file__).parent.parent / "examples" / "expected-output"


def _load(name: str) -> dict:
    return json.loads((EXPECTED / name).read_text())


def test_summarize_host() -> None:
    summary = summarize_host(_load("engin-host.json"))
    assert summary["host"] == "P. pastoris"
    assert summary["score"] == pytest.approx(0.8294, abs=1e-3)
    assert summary["confidence"] == pytest.approx(0.6811, abs=1e-3)
    assert summary["provenance"] == "illustrative"
    assert "secretion" in summary["key_drivers"]


def test_summarize_pathway_top_routes_overlap() -> None:
    summary = summarize_pathway(_load("engin-pathway.json"))
    assert summary["separated"] is False  # route-A and route-B intervals overlap
    assert summary["trained_on"] == "synthetic generator"
    assert summary["routes"][0]["route_id"] == "route-A"


def test_summarize_process() -> None:
    summary = summarize_process(_load("engin-process.json"))
    assert summary["prob_meets_target"] == 1.0
    assert summary["expected_usd_per_kg"] == pytest.approx(49.89, abs=0.01)
    assert len(summary["recommended"]) == 4


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((0.532, 0.754), (0.524, 0.747), True),  # route-A vs route-B: overlap
        ((0.0, 0.1), (0.2, 0.3), False),  # disjoint
        ((0.0, 0.5), (0.5, 1.0), True),  # touching endpoints count as overlap
    ],
)
def test_intervals_overlap(a: tuple, b: tuple, expected: bool) -> None:
    assert intervals_overlap(a, b) is expected
