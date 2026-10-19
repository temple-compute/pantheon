#!/usr/bin/env python3
"""
Download a structure from the RCSB PDB: https://files.rcsb.org/download/<ID>.pdb,
or, with an empty --pdb-id, copy the --upload file instead.

Standalone block: its output is a plain .pdb. Runs on the orchestrator (cluster
compute nodes often have no internet). Stdlib only.
"""

import argparse
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path


def pdb_url(pdb_id: str) -> str:
    pdb_id = pdb_id.strip().upper()
    if not re.fullmatch(r"[0-9][A-Z0-9]{3}", pdb_id):
        raise SystemExit(f"Not a PDB ID: {pdb_id!r} (expected 4 characters, e.g. 3HTB).")
    return f"https://files.rcsb.org/download/{pdb_id}.pdb"


def fetch(url: str, dest: Path, attempts: int = 3) -> None:
    err = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            if b"ATOM  " not in data and b"HETATM" not in data:
                raise SystemExit(f"{url} returned no coordinates.")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise SystemExit(f"{url}: not found. Large entries are mmCIF-only at RCSB; "
                                 "convert to PDB and connect the file instead.")
            err = e
        except OSError as e:
            err = e
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Could not download {url}: {err}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdb-id", required=True)
    ap.add_argument("--upload", type=Path, help="PDB to use when --pdb-id is empty")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not a.pdb_id.strip():
        if a.upload is None:
            raise SystemExit("pdb_id is empty and no structure was uploaded.")
        a.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.upload, a.out)
        print(f"Using uploaded structure {a.upload} -> {a.out}")
        return
    url = pdb_url(a.pdb_id)
    fetch(url, a.out)
    print(f"Downloaded {url} -> {a.out}")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        assert pdb_url(" 3htb ") == "https://files.rcsb.org/download/3HTB.pdb"
        for bad in ("3HT", "ABCD", "3HTB1"):
            try:
                pdb_url(bad)
            except SystemExit:
                continue
            raise AssertionError(bad)
        print("fetch_pdb.py: self-check OK")
    else:
        main()
