#!/usr/bin/env python3
"""Draft computable rules from the protocol text with Claude, and diff them
against the human-reviewed rule set.

Nothing downstream reads the draft: examples/criteria.reviewed.json is the
review gate. This task only shows how far an LLM draft is from it.

If ANTHROPIC_API_KEY is not set, the call is skipped and both outputs record
`status: skipped`. The model comes from config.json (`llm.model`).

Usage:
    python parse_criteria.py --protocol NCT.json --reviewed criteria.reviewed.json \
        --config config.json --draft criteria_draft.json --diff criteria_diff.json
    python parse_criteria.py --selftest
"""

import argparse
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

NULLABLE = lambda t: {"anyOf": [t, {"type": "null"}]}  # noqa: E731
SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": ["inclusion", "exclusion"]},
                    "field": NULLABLE({"type": "string"}),
                    "codes": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"system": {"type": "string", "enum": ["SNOMED", "LOINC", "RxNorm"]}, "code": {"type": "string"}},
                        "required": ["system", "code"], "additionalProperties": False}},
                    "operator": NULLABLE({"type": "string", "enum": ["between", "gte", "within_days", "is_true", "equals"]}),
                    "value": {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "array", "items": {"type": "number"}}, {"type": "null"}]},
                    "lookback_days": NULLABLE({"type": "integer"}),
                    "computable": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "text", "type", "field", "codes", "operator", "value", "lookback_days", "computable", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["criteria"],
    "additionalProperties": False,
}
COMPARED = ["type", "field", "operator", "value", "lookback_days", "computable"]


def prompt(eligibility: str, features: dict) -> str:
    catalog = "\n".join(f"- {k}: {v['kind']}" + (f" ({v['note']})" if v.get("note") else "") for k, v in features.items())
    return f"""Convert these clinical trial eligibility criteria into computable rules for an EHR-style synthetic population.

Split the text into one rule per bullet (split a bullet into two rules only if it has two independent conditions).
Use only these patient fields (plus `age` in years):
{catalog}

Operators: between [low, high]; gte number; within_days number (field is days since an event or a drug, true if <= value); is_true (boolean field); equals (text field).
Mark a rule computable=false, with field/operator/value null, when it cannot be evaluated from these fields (for example consent or protocol compliance), and say why in `reason`.
Give the standard SNOMED CT, LOINC or RxNorm codes you would use for each rule.

Eligibility criteria:
{eligibility}"""


def call_claude(eligibility: str, features: dict, model: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # on a policy decline, re-run on a fallback model in the same call
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt(eligibility, features)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    text = next(b.text for b in response.content if b.type == "text")
    return {"status": "ok", "model": response.model, **json.loads(text)}


def _norm(v):
    if isinstance(v, list):
        return [float(x) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


def diff(draft: list[dict], reviewed: list[dict]) -> dict:
    rows, used = [], set()
    for r in reviewed:
        scores = [(difflib.SequenceMatcher(None, r["text"].lower(), d["text"].lower()).ratio(), i) for i, d in enumerate(draft) if i not in used]
        score, i = max(scores, default=(0.0, None))
        if i is None or score < 0.5:
            rows.append({"id": r["id"], "matched": None, "agrees": False, "differences": ["no matching draft rule"]})
            continue
        used.add(i)
        d = draft[i]
        diffs = [f"{k}: draft={d.get(k)!r} reviewed={r.get(k)!r}" for k in COMPARED if _norm(d.get(k)) != _norm(r.get(k))]
        rows.append({"id": r["id"], "matched": d["id"], "agrees": not diffs, "differences": diffs})
    extra = [draft[i]["id"] for i in range(len(draft)) if i not in used]
    return {"status": "ok", "n_reviewed": len(reviewed), "n_draft": len(draft),
            "n_agree": sum(x["agrees"] for x in rows), "unmatched_draft": extra, "criteria": rows}


def run(args) -> int:
    protocol = json.loads(Path(args.protocol).read_text())
    reviewed = json.loads(Path(args.reviewed).read_text())
    model = json.loads(Path(args.config).read_text())["llm"]["model"]
    eligibility = protocol["protocolSection"]["eligibilityModule"]["eligibilityCriteria"]
    if not os.environ.get("ANTHROPIC_API_KEY"):
        msg = "ANTHROPIC_API_KEY not set: skipping LLM draft; downstream tasks use the reviewed rule set."
        print(f"parse_criteria: {msg}")
        draft = {"status": "skipped", "message": msg}
        result = {"status": "skipped", "message": msg}
    else:
        try:
            draft = call_claude(eligibility, reviewed["features"], model)
            result = {"model": draft["model"], **diff(draft["criteria"], reviewed["criteria"])}
            print(f"parse_criteria: {result['n_agree']}/{result['n_reviewed']} reviewed rules match the {model} draft")
        except Exception as e:  # the draft is advisory; never block the pipeline on it
            msg = f"LLM draft failed ({type(e).__name__}: {e}); downstream tasks use the reviewed rule set."
            print(f"parse_criteria: {msg}")
            draft = {"status": "error", "message": msg}
            result = {"status": "error", "message": msg}
    Path(args.draft).parent.mkdir(parents=True, exist_ok=True)
    Path(args.draft).write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n")
    Path(args.diff).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


def _selftest() -> int:
    reviewed = [
        {"id": "I1", "text": "Signed informed consent", "type": "inclusion", "computable": False},
        {"id": "I3", "text": "eGFR >=25 and <=75 at visit 1", "type": "inclusion", "field": "egfr", "operator": "between", "value": [25, 75], "lookback_days": 365, "computable": True},
    ]
    draft = [
        {"id": "a", "text": "eGFR ≥25 and ≤75 at visit 1", "type": "inclusion", "field": "egfr", "operator": "between", "value": [25.0, 75.0], "lookback_days": 30, "computable": True},
        {"id": "b", "text": "Signed informed consent", "type": "inclusion", "field": None, "operator": None, "value": None, "lookback_days": None, "computable": False},
        {"id": "c", "text": "Something unrelated entirely", "type": "exclusion", "computable": True},
    ]
    d = diff(draft, reviewed)
    by = {r["id"]: r for r in d["criteria"]}
    assert by["I1"]["agrees"] and by["I1"]["matched"] == "b"
    assert not by["I3"]["agrees"] and by["I3"]["differences"] == ["lookback_days: draft=30 reviewed=365"]
    assert d["unmatched_draft"] == ["c"] and d["n_agree"] == 1
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "p.json").write_text(json.dumps({"protocolSection": {"eligibilityModule": {"eligibilityCriteria": "x"}}}))
        (t / "r.json").write_text(json.dumps({"features": {}, "criteria": reviewed}))
        (t / "c.json").write_text(json.dumps({"llm": {"model": "m"}}))
        key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            run(argparse.Namespace(protocol=t / "p.json", reviewed=t / "r.json", config=t / "c.json", draft=t / "d.json", diff=t / "x.json"))
        finally:
            if key is not None:
                os.environ["ANTHROPIC_API_KEY"] = key
        assert json.loads((t / "x.json").read_text())["status"] == "skipped"
    assert "egfr" in prompt("x", {"egfr": {"kind": "lab_latest"}})
    print("parse_criteria selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("--protocol", "--reviewed", "--config", "--draft", "--diff"):
        ap.add_argument(a)
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not all((a.protocol, a.reviewed, a.config, a.draft, a.diff)):
        ap.error("--protocol, --reviewed, --config, --draft and --diff are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
