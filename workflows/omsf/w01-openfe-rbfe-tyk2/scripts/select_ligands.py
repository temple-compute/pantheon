#!/usr/bin/env python3
# Picks the ligands for this profile from the TYK2 SDF before charging, so the
# smoke run only pays AM1-BCC for 3 molecules. Stdlib only.

import argparse
import sys
from pathlib import Path

# Three ligands give a minimal spanning network of 2 edges, i.e. 4 legs.
SMOKE = ["lig_ejm_31", "lig_ejm_42", "lig_ejm_46"]


def records(text: str) -> list[str]:
    """Split an SDF into records, each ending with its '$$$$' line."""
    out, buf = [], []
    for line in text.splitlines(keepends=True):
        buf.append(line)
        if line.strip() == "$$$$":
            out.append("".join(buf))
            buf = []
    return out


def select(text: str, profile: str) -> str:
    recs = records(text)
    if profile == "full":
        return "".join(recs)
    by_name = {r.splitlines()[0].strip(): r for r in recs}
    missing = [n for n in SMOKE if n not in by_name]
    if missing:
        raise SystemExit(f"ligands not in input SDF: {missing}")
    return "".join(by_name[n] for n in SMOKE)


def selftest() -> None:
    sdf = "".join(f"{n}\n  x\n\nM  END\n$$$$\n" for n in ["a", *SMOKE, "b"])
    assert len(records(sdf)) == 5
    assert select(sdf, "full") == sdf
    smoke = select(sdf, "smoke")
    assert [r.splitlines()[0] for r in records(smoke)] == SMOKE
    try:
        select("a\n$$$$\n", "smoke")
    except SystemExit:
        pass
    else:
        raise AssertionError("missing ligands must fail")
    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ligands", type=Path, required=True)
    ap.add_argument("--profile", choices=["smoke", "full"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(select(a.ligands.read_text(), a.profile))


if __name__ == "__main__":
    main()
