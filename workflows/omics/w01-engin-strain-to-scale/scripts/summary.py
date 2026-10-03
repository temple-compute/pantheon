#!/usr/bin/env python3
"""Merge Engin's three stage JSONs into one decision brief.

engin-host, engin-pathway and engin-process each read the same project.yaml
and answer their own question independently -- this stage is the only place
that reads across all three. The pure helpers below (summarize_* and
intervals_overlap) do the merging; everything else is argv/file I/O so the
helpers can be tested directly (see test_summary.py).
"""

import argparse
import json
from pathlib import Path
from typing import Any

CAVEATS = """## How to read this

Engin is honest about being early -- these caveats are the point of the tool,
not fine print:

- **The calibration transfers; the point prediction does not.** Measured
  against 406 real industrial fermentation batches, interval coverage lands
  near its 90% nominal, while predictive R² collapses to roughly 0.02-0.11.
  Trust the error bars, not the centre of the bar.
- **engin-host's knowledge base is illustrative.** Capability values are
  hand-assigned with no citations behind them; the ranking demonstrates the
  scoring machinery, not evidence about these organisms.
- **engin-pathway is trained on a synthetic route generator**, and the step
  features are your own judgement entered by hand. Read the order as a
  prompt for discussion, not a measurement.
- **engin-process optimises net $/kg, not titer**, and its runs are
  simulated from the vessel model in your project file, not read from real
  run history.
"""


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Whether closed intervals *a* and *b* share any point."""
    a_lo, a_hi = a
    b_lo, b_hi = b
    return a_lo <= b_hi and b_lo <= a_hi


def summarize_host(doc: dict[str, Any]) -> dict[str, Any]:
    """Pull the recommendation and top rows out of an engin-host JSON doc."""
    decision = doc["decision"]
    return {
        "host": decision["host"],
        "score": decision["score"],
        "band90": decision["band90"],
        "confidence": decision["confidence"],
        "key_drivers": decision["key_drivers"],
        "alternatives": decision["alternatives"],
        "provenance": doc["ranking"][0]["provenance"],
        "flags": doc["ranking"][0]["flags"],
    }


def summarize_pathway(doc: dict[str, Any]) -> dict[str, Any]:
    """Pull the ranking and shortlist-vs-winner call out of an engin-pathway doc."""
    ranking = doc["ranking"]
    top_two = ranking[:2]
    separated = (
        not intervals_overlap(
            (top_two[0]["lo"], top_two[0]["hi"]), (top_two[1]["lo"], top_two[1]["hi"])
        )
        if len(top_two) == 2
        else True
    )
    return {
        "routes": [
            {
                "route_id": r["route_id"],
                "manufacturability": r["manufacturability"],
                "interval": [r["lo"], r["hi"]],
            }
            for r in ranking
        ],
        "separated": separated,
        "trained_on": doc["trained_on"],
        "n_labelled_supplied": doc["n_labelled_supplied"],
    }


def summarize_process(doc: dict[str, Any]) -> dict[str, Any]:
    """Pull the best-known cost and recommended runs out of an engin-process doc."""
    best = doc["best_known"]
    return {
        "expected_usd_per_kg": best["expected_usd_per_kg"],
        "interval": [best["lower_usd_per_kg"], best["upper_usd_per_kg"]],
        "prob_meets_target": best["prob_meets_target"],
        "target_usd_per_kg": best["target_usd_per_kg"],
        "recommended": doc["recommended"],
    }


def render_markdown(target: str, host: dict, pathway: dict, process: dict) -> str:
    lines = [f"# Decision brief -- {target}", ""]

    lines += [
        "## Host (engin-host)",
        f"**{host['host']}**, score {host['score']:.2f} ± {host['band90']:.2f} "
        f"(confidence {host['confidence']:.2f}). "
        f"Driven by {', '.join(host['key_drivers'])}.",
        f"Alternatives: {', '.join(host['alternatives'])}.",
        f"_Basis: {host['provenance']}._",
        "",
    ]

    route_lines = [
        f"- {r['route_id']}: {r['manufacturability']:.3f} "
        f"[{r['interval'][0]:.3f}, {r['interval'][1]:.3f}]"
        for r in pathway["routes"]
    ]
    verdict = (
        "Top routes are separated: read the order as a ranking."
        if pathway["separated"]
        else "Top routes' intervals overlap: a shortlist, not a winner."
    )
    lines += ["## Pathway (engin-pathway)", *route_lines, "", verdict, ""]

    reco_lines = [
        f"{i}. E[saving]=${r['expected_cost_reduction_usd_per_kg']:.2f}/kg  "
        f"feed_rate={r['feed_rate']:.4f}  feed_start={r['feed_start']:.2f}  "
        f"Sf={r['Sf']:.0f}  induction_time={r['induction_time']:.2f}  S0={r['S0']:.1f}"
        for i, r in enumerate(process["recommended"], start=1)
    ]
    lines += [
        "## Process (engin-process)",
        f"Best known cost: ${process['expected_usd_per_kg']:.2f}/kg "
        f"[${process['interval'][0]:.2f}, ${process['interval'][1]:.2f}] (90%). "
        f"Clears ${process['target_usd_per_kg']:.0f}/kg target with "
        f"probability {process['prob_meets_target']:.2f}.",
        "",
        "Next runs, by expected cost reduction:",
        *reco_lines,
        "",
        CAVEATS,
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--pathway", required=True, type=Path)
    parser.add_argument("--process", required=True, type=Path)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    args = parser.parse_args()

    host_doc = json.loads(args.host.read_text())
    pathway_doc = json.loads(args.pathway.read_text())
    process_doc = json.loads(args.process.read_text())

    host = summarize_host(host_doc)
    pathway = summarize_pathway(pathway_doc)
    process = summarize_process(process_doc)
    target = host_doc.get("target", pathway_doc.get("target", process_doc.get("target")))

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(
            {"target": target, "host": host, "pathway": pathway, "process": process},
            indent=2,
        )
        + "\n"
    )
    args.out_md.write_text(render_markdown(target, host, pathway, process) + "\n")


if __name__ == "__main__":
    main()
