#!/usr/bin/env python3
"""Split the population request into one folder per Synthea shard.

Each shard_NN/params.json is one item for the generate_population map: the
engine runs one clone per child folder. Shard i gets seed `seed + i` and
`size // shards` patients (the first `size % shards` shards get one more).
If `population.synthea_csv` is set, a single `import` shard is written
instead, pointing at that existing Synthea CSV folder, so the DAG keeps its
shape and generation is skipped.

Usage:
    python3 plan_shards.py --config config.json --out shards/
    python3 plan_shards.py --selftest
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path


def plan(pop: dict, index_date: str) -> list[dict]:
    if pop.get("synthea_csv"):
        return [{"mode": "import", "csv_dir": str(Path(pop["synthea_csv"]).expanduser().resolve())}]
    size, shards, seed = int(pop["size"]), int(pop["shards"]), int(pop["seed"])
    if shards < 1 or size < shards:
        raise ValueError("need 1 <= shards <= size")
    base, extra = divmod(size, shards)
    return [
        {
            "mode": "generate",
            "shard": i,
            "size": base + (1 if i < extra else 0),
            "seed": seed + i,
            "clinician_seed": seed + i,
            "state": pop.get("state", "Massachusetts"),
            "age_range": pop.get("age_range"),
            "modules": pop.get("modules"),
            "java_heap": pop.get("java_heap", "2g"),
            "reference_date": index_date.replace("-", ""),
        }
        for i in range(shards)
    ]


def write(shards: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    width = max(2, len(str(len(shards) - 1)))
    for i, params in enumerate(shards):
        d = out / f"shard_{i:0{width}d}"
        d.mkdir(exist_ok=True)
        (d / "params.json").write_text(json.dumps(params, indent=2) + "\n")


def run(args) -> int:
    cfg = json.loads(Path(args.config).read_text())
    shards = plan(cfg["population"], cfg["index_date"])
    write(shards, Path(args.out))
    print(f"plan_shards: wrote {len(shards)} shard(s) to {args.out}")
    return 0


def _selftest() -> int:
    s = plan({"size": 10, "shards": 3, "seed": 5}, "2026-01-01")
    assert [x["size"] for x in s] == [4, 3, 3] and sum(x["size"] for x in s) == 10
    assert [x["seed"] for x in s] == [5, 6, 7] and s[0]["reference_date"] == "20260101"
    imp = plan({"size": 10, "shards": 3, "seed": 5, "synthea_csv": "/tmp/x"}, "2026-01-01")
    assert len(imp) == 1 and imp[0]["mode"] == "import"
    with tempfile.TemporaryDirectory() as tmp:
        write(s, Path(tmp))
        assert sorted(p.name for p in Path(tmp).iterdir()) == ["shard_00", "shard_01", "shard_02"]
    try:
        plan({"size": 2, "shards": 3, "seed": 1}, "2026-01-01")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("plan_shards selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config")
    ap.add_argument("--out")
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.config and a.out):
        ap.error("--config and --out are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
