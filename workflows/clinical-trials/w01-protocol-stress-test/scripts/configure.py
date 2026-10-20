#!/usr/bin/env python3
"""Write the run config: config.json with the campaign inputs laid over it.

The typed workflow inputs (population size, shards, seed, state, index date,
variant batch size, random combinations, LLM model) replace the matching keys
of the uploaded config.json; every other key (age_range, modules, java_heap,
synthea_csv, random_seed) is kept as uploaded.

Usage:
    python3 configure.py --base config.json --out config.json --size 5000 ...
    python3 configure.py --selftest
"""

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path


def configure(base: dict, a: argparse.Namespace) -> dict:
    date.fromisoformat(a.index_date)  # raises on a bad date, naming the value
    cfg = json.loads(json.dumps(base))
    pop = cfg.setdefault("population", {})
    pop.update(size=int(a.size), shards=int(a.shards), seed=int(a.seed), state=a.state)
    if pop["shards"] > pop["size"]:
        raise ValueError(f"population_shards ({pop['shards']}) must not exceed population_size ({pop['size']})")
    cfg.setdefault("variants", {}).update(batch_size=int(a.batch_size), random_combinations=int(a.random_combinations))
    cfg.setdefault("llm", {})["model"] = a.llm_model
    cfg["index_date"] = a.index_date
    return cfg


def _args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base")
    ap.add_argument("--out")
    # float() first: a number input may render as 5000.0
    for k in ("size", "shards", "seed", "batch-size", "random-combinations"):
        ap.add_argument(f"--{k}", type=lambda s: int(float(s)))
    ap.add_argument("--state")
    ap.add_argument("--index-date")
    ap.add_argument("--llm-model")
    ap.add_argument("--selftest", action="store_true")
    return ap.parse_args(argv)


def _selftest() -> int:
    base = {"index_date": "2026-01-01", "population": {"size": 5000, "shards": 4, "seed": 42, "java_heap": "2g"},
            "variants": {"batch_size": 50, "random_combinations": 0, "random_seed": 7}, "llm": {"model": "m"}}
    a = _args("--size 200.0 --shards 2 --seed 1 --batch-size 20 --random-combinations 0 --state Ohio "
              "--index-date 2025-06-30 --llm-model x".split())
    cfg = configure(base, a)
    assert cfg["population"] == {"size": 200, "shards": 2, "seed": 1, "state": "Ohio", "java_heap": "2g"}, cfg
    assert cfg["variants"]["random_seed"] == 7 and cfg["variants"]["batch_size"] == 20
    assert cfg["index_date"] == "2025-06-30" and cfg["llm"]["model"] == "x" and base["population"]["size"] == 5000
    for bad in ("--shards 300", "--index-date 2025-13-01"):
        b = _args((" ".join(f"--{k} {v}" for k, v in vars(a).items() if v not in (None, False)).replace("_", "-") + " " + bad).split())
        try:
            configure(base, b)
        except ValueError:
            continue
        raise AssertionError(bad)
    print("configure selftest OK")
    return 0


def main(argv=None) -> int:
    a = _args(argv)
    if a.selftest:
        return _selftest()
    cfg = configure(json.loads(Path(a.base).read_text()), a)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(cfg, indent=2) + "\n")
    print(json.dumps({k: cfg[k] for k in ("index_date", "population", "variants")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
