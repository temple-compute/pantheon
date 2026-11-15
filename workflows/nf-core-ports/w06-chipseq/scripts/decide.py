#!/usr/bin/env python3
"""
The nf-core/chipseq Groovy decisions after peak calling, as one script.

``peaks``: BAM_PEAKS_CALL_QC_ANNOTATE_MACS3_HOMER keeps IP samples whose MACS3
peak file is not empty (``peaks.size() > 0``). Writes

- ``peak_pass/<id>``: the IP sample's meta file, for every kept sample;
- ``antibodies/<antibody>``: one meta file per antibody with kept peaks, as
  BED_CONSENSUS_QUANTIFY_QC_BEDTOOLS_FEATURECOUNTS_DESEQ2 groups them:
  ``peaks`` (kept sample ids), ``bams`` (every IP sample id of the antibody),
  ``multiple_groups`` (more than one ``id - ~/_REP\\d+$/`` group) and
  ``replicates_exist`` (a group with more than one sample).

stdlib only.

Usage:
    decide.py peaks --ips ips/ --macs3 macs3/ --suffix _peaks.broadPeak \\
        --peak-pass peak_pass/ --antibodies antibodies/
    decide.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

REP_RE = re.compile(r"_REP\d+$")


def read_meta(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        k, _, v = line.partition("=")
        out[k] = v.strip('"')
    return out


def find_peak(macs3: Path, sid: str, suffix: str) -> Path:
    hits = list(macs3.glob(f"*/{sid}{suffix}"))
    if len(hits) != 1:
        raise SystemExit(f"{sid}: expected one {sid}{suffix} under {macs3}, found {len(hits)}")
    return hits[0]


def antibody_meta(peaks: list[str], bams: list[str]) -> str:
    groups = Counter(REP_RE.sub("", sid) for sid in peaks)
    multiple = len(groups) > 1
    reps = max(groups.values()) > 1
    return (
        f'peaks="{" ".join(sorted(peaks))}"\n'
        f'bams="{" ".join(sorted(bams))}"\n'
        f"multiple_groups={'true' if multiple else 'false'}\n"
        f"replicates_exist={'true' if reps else 'false'}\n"
    )


def decide_peaks(args: argparse.Namespace) -> None:
    ips, macs3 = Path(args.ips), Path(args.macs3)
    peak_pass, antibodies = Path(args.peak_pass), Path(args.antibodies)
    peak_pass.mkdir(parents=True, exist_ok=True)
    antibodies.mkdir(parents=True, exist_ok=True)
    kept: dict[str, list[str]] = {}
    bams: dict[str, list[str]] = {}
    for meta in sorted(ips.iterdir()):
        m = read_meta(meta)
        bams.setdefault(m["antibody"], []).append(meta.name)
        if find_peak(macs3, meta.name, args.suffix).stat().st_size > 0:
            (peak_pass / meta.name).write_text(meta.read_text())
            kept.setdefault(m["antibody"], []).append(meta.name)
    for ab, peaks in kept.items():
        (antibodies / ab).write_text(antibody_meta(peaks, bams[ab]))


def selftest() -> None:
    assert "multiple_groups=true\nreplicates_exist=true" in antibody_meta(["A_T0_REP1", "A_T0_REP2", "A_T15_REP1"], [])
    assert "multiple_groups=false\nreplicates_exist=false" in antibody_meta(["A_T0_REP1"], [])
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for sid, size in (("A_REP1", 5), ("A_REP2", 0), ("B_REP1", 3)):
            (t / "ips").mkdir(exist_ok=True)
            (t / "ips" / sid).write_text(f"antibody={sid[0]}\ncontrol=IN_REP1\n")
            (t / "macs3" / "0").mkdir(parents=True, exist_ok=True)
            (t / "macs3" / "0" / f"{sid}_peaks.broadPeak").write_text("x" * size)
        ns = argparse.Namespace(ips=t / "ips", macs3=t / "macs3", suffix="_peaks.broadPeak", peak_pass=t / "pp", antibodies=t / "ab")
        decide_peaks(ns)
        assert sorted(p.name for p in (t / "pp").iterdir()) == ["A_REP1", "B_REP1"]
        a = read_meta(t / "ab" / "A")
        assert a["peaks"] == "A_REP1" and a["bams"] == "A_REP1 A_REP2" and a["replicates_exist"] == "false"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("peaks")
    for key in ("ips", "macs3", "suffix", "peak-pass", "antibodies"):
        p.add_argument(f"--{key}", required=True)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.cmd == "peaks":
        decide_peaks(args)
    else:
        ap.error("pick peaks or --selftest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
