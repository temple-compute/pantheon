#!/usr/bin/env python3
"""Enumerate protocol variants and write them as batch files for the evaluate map.

A variant's params map each applied computable criterion to its value; a
removed criterion is simply absent.
Kinds, in order:
  baseline  every criterion at its reviewed value
  loo       leave-one-out: one criterion removed
  sweep     full grid over each criterion's `sweep` values (others at baseline)
  random    optional seeded random combinations (variants.random_combinations)
Each variant's hash is the first 12 hex chars of the SHA-256 of its params as
canonical JSON; duplicates (same params) keep their first occurrence.

Usage:
    python generate_variants.py --rules criteria.json --config config.json --out variants/
    python generate_variants.py --selftest
"""

import argparse
import hashlib
import itertools
import json
import random
import sys
import tempfile
from pathlib import Path


def sweep_values(c: dict) -> list:
    s = c.get("sweep")
    if not s:
        return []
    if c["operator"] == "between":
        return [[lo, hi] for lo in s["low"] for hi in s["high"] if lo < hi]
    return list(s["value"])


def vhash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


def enumerate_variants(rules: dict, n_random: int = 0, seed: int = 0) -> list[dict]:
    crit = [c for c in rules["criteria"] if c.get("computable")]
    base = {c["id"]: c.get("value") for c in crit}
    out = [("baseline", "baseline", dict(base))]
    out += [("loo", f"remove {c['id']}", {k: v for k, v in base.items() if k != c["id"]}) for c in crit]
    swept = [c for c in crit if sweep_values(c)]
    for combo in itertools.product(*(sweep_values(c) for c in swept)):
        p = {**base, **{c["id"]: v for c, v in zip(swept, combo)}}
        out.append(("sweep", ", ".join(f"{c['id']}={json.dumps(v)}" for c, v in zip(swept, combo)), p))
    rng = random.Random(seed)
    for _ in range(n_random):
        p = {}
        for c in crit:
            options = sweep_values(c) or [c.get("value")]
            if rng.random() >= 0.2:  # each criterion is removed with probability 0.2
                p[c["id"]] = rng.choice(options)
        out.append(("random", "random", p))
    seen, variants = set(), []
    for kind, label, p in out:
        h = vhash(p)
        if h in seen:
            continue
        seen.add(h)
        variants.append({"variant_id": f"v{len(variants):05d}", "hash": h, "kind": kind, "label": label, "params": p})
    return variants


def write_batches(variants: list[dict], out: Path, batch_size: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    batches = [variants[i : i + batch_size] for i in range(0, len(variants), batch_size)]
    width = max(3, len(str(len(batches) - 1)))
    for i, b in enumerate(batches):
        (out / f"batch_{i:0{width}d}.json").write_text(json.dumps(b, indent=1) + "\n")
    return len(batches)


def run(args) -> int:
    rules = json.loads(Path(args.rules).read_text())
    vc = json.loads(Path(args.config).read_text())["variants"]
    variants = enumerate_variants(rules, int(vc.get("random_combinations", 0)), int(vc.get("random_seed", 0)))
    n = write_batches(variants, Path(args.out), int(vc["batch_size"]))
    kinds = {k: sum(v["kind"] == k for v in variants) for k in ("baseline", "loo", "sweep", "random")}
    print(f"generate_variants: {len(variants)} variants {kinds} in {n} batches")
    return 0


def _selftest() -> int:
    rules = {"criteria": [
        {"id": "A", "computable": True, "operator": "between", "value": [25, 75], "sweep": {"low": [20, 25], "high": [75, 90]}},
        {"id": "B", "computable": True, "operator": "gte", "value": 28, "sweep": {"value": [0, 28]}},
        {"id": "C", "computable": True, "operator": "is_true"},
        {"id": "X", "computable": False},
    ]}
    v = enumerate_variants(rules)
    assert v[0]["kind"] == "baseline" and v[0]["params"] == {"A": [25, 75], "B": 28, "C": None}
    assert [x["label"] for x in v if x["kind"] == "loo"] == ["remove A", "remove B", "remove C"]
    assert "C" not in v[3]["params"] and v[3]["label"] == "remove C"
    # grid is 2x2 for A times 2 for B = 8, minus the one equal to baseline
    assert sum(x["kind"] == "sweep" for x in v) == 7
    assert len({x["hash"] for x in v}) == len(v)
    assert enumerate_variants(rules, 5, 1) == enumerate_variants(rules, 5, 1)
    with tempfile.TemporaryDirectory() as tmp:
        assert write_batches(v, Path(tmp), 4) == 3
        assert sum(len(json.loads(p.read_text())) for p in Path(tmp).iterdir()) == len(v)
    print("generate_variants selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for a in ("--rules", "--config", "--out"):
        ap.add_argument(a)
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.rules and a.config and a.out):
        ap.error("--rules, --config and --out are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
