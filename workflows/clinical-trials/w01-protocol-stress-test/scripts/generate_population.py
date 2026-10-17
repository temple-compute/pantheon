#!/usr/bin/env python3
"""Generate (or import) one shard of the synthetic population with Synthea.

Reads shard params.json written by plan_shards.py and writes the CSV tables
build_features needs (patients, conditions, observations, medications,
procedures) plus provenance.json into --out.

Synthea is the pinned v4.0.0 release jar, downloaded once into
$PANTHEON_CACHE (default ~/.cache/pantheon) and verified against its
published SHA-256 before every use. Java comes from the jdk4py wheel in the
task's uv environment, so no system JDK is needed.

Usage:
    python generate_population.py --shard shard_00/ --out population/00/
    python generate_population.py --selftest
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SYNTHEA_VERSION = "v4.0.0"
JAR_URL = f"https://github.com/synthetichealth/synthea/releases/download/{SYNTHEA_VERSION}/synthea-with-dependencies.jar"
JAR_SHA256 = "ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1"
TABLES = ["patients", "conditions", "observations", "medications", "procedures"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_jar(cache: Path, url: str = JAR_URL, expected: str = JAR_SHA256) -> Path:
    """Return a verified jar path, downloading it on first use."""
    jar = cache / "synthea" / SYNTHEA_VERSION / "synthea-with-dependencies.jar"
    if not jar.exists():
        jar.parent.mkdir(parents=True, exist_ok=True)
        print(f"generate_population: downloading {url}", flush=True)
        # Unique temp name + atomic rename: concurrent shards may download at once.
        fd, tmp = tempfile.mkstemp(dir=jar.parent, suffix=".part")
        os.close(fd)
        try:
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, jar)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    got = sha256(jar)
    if got != expected:
        raise SystemExit(f"generate_population: checksum mismatch for {jar}: {got} != {expected}. Delete it and re-run.")
    return jar


def java_bin() -> str:
    import jdk4py  # provided by the uv environment

    return str(jdk4py.JAVA)


def synthea_cmd(java: str, jar: Path, p: dict, outdir: Path) -> list[str]:
    cmd = [
        java, f"-Xmx{p.get('java_heap', '2g')}", "-jar", str(jar),
        "-s", str(p["seed"]), "-cs", str(p["clinician_seed"]), "-p", str(p["size"]),
        # Pin the simulation clock so the same seed gives the same patients.
        "-r", p["reference_date"], "-e", p["reference_date"],
        f"--exporter.baseDirectory={outdir}",
        "--exporter.csv.export=true",
        "--exporter.csv.included_files=" + ",".join(f"{t}.csv" for t in TABLES),
        "--exporter.fhir.export=false",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
    ]
    if p.get("age_range"):
        cmd += ["-a", p["age_range"]]
    if p.get("modules"):
        cmd += ["-m", ":".join(p["modules"])]
    cmd.append(p["state"])
    return cmd


def copy_tables(src: Path, out: Path, move: bool = False) -> None:
    missing = [t for t in TABLES if not (src / f"{t}.csv").exists()]
    if missing:
        raise SystemExit(f"generate_population: {src} is missing {', '.join(m + '.csv' for m in missing)}")
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        (shutil.move if move else shutil.copyfile)(src / f"{t}.csv", out / f"{t}.csv")


def run(args) -> int:
    shard = Path(args.shard)
    p = json.loads((shard / "params.json").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if p["mode"] == "import":
        copy_tables(Path(p["csv_dir"]), out)
        prov = {"mode": "import", "source": p["csv_dir"]}
    else:
        jar = ensure_jar(Path(os.environ.get("PANTHEON_CACHE", Path.home() / ".cache" / "pantheon")))
        # Scratch in the task's cwd, not next to `out`: siblings of `out` are other map slots.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            cmd = synthea_cmd(java_bin(), jar, p, Path(tmp))
            print("generate_population:", " ".join(cmd), flush=True)
            r = subprocess.run(cmd, cwd=tmp)
            if r.returncode != 0:
                raise SystemExit(f"generate_population: Synthea exited with {r.returncode}")
            copy_tables(Path(tmp) / "csv", out, move=True)
        prov = {
            "mode": "generate", "synthea_version": SYNTHEA_VERSION, "jar_sha256": JAR_SHA256,
            **{k: p[k] for k in ("shard", "size", "seed", "clinician_seed", "state", "age_range", "modules", "reference_date")},
        }
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
    print(f"generate_population: wrote {', '.join(TABLES)} to {out}")
    return 0


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Checksum gate: a cached jar with the wrong content is rejected.
        jar = tmp / "synthea" / SYNTHEA_VERSION / "synthea-with-dependencies.jar"
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"not a jar")
        assert ensure_jar(tmp, expected=hashlib.sha256(b"not a jar").hexdigest()) == jar
        try:
            ensure_jar(tmp)
            raise AssertionError("expected checksum failure")
        except SystemExit as e:
            assert "checksum mismatch" in str(e)
        # Import mode copies the five tables and records the source.
        src = tmp / "csv"
        src.mkdir()
        for t in TABLES:
            (src / f"{t}.csv").write_text("Id\n")
        (tmp / "shard").mkdir()
        (tmp / "shard" / "params.json").write_text(json.dumps({"mode": "import", "csv_dir": str(src)}))
        assert run(argparse.Namespace(shard=tmp / "shard", out=tmp / "out")) == 0
        assert sorted(p.name for p in (tmp / "out").iterdir()) == sorted([f"{t}.csv" for t in TABLES] + ["provenance.json"])
        cmd = synthea_cmd("java", jar, {"seed": 1, "clinician_seed": 1, "size": 5, "reference_date": "20260101",
                                        "state": "Utah", "age_range": "18-100", "modules": ["diabetes"]}, tmp)
        assert cmd[-1] == "Utah" and "-a" in cmd and "-m" in cmd and "20260101" in cmd
    print("generate_population selftest OK")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shard")
    ap.add_argument("--out")
    ap.add_argument("--selftest", "--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.shard and a.out):
        ap.error("--shard and --out are required")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
