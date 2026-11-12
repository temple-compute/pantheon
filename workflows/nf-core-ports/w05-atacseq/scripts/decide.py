#!/usr/bin/env python3
"""
The Groovy-side grouping of nf-core/atacseq 2.1.2 as one file-in/file-out step.

``trimmed`` reads the per-run meta files (``runs/<id>``, bash-sourceable
``key=value``) and the TrimGalore reports, and writes three lists of meta
files that the per-run, per-library and per-replicate ``horus_map`` stages
iterate over:

- ``trim_pass/<run>``: runs with at least ``min_trimmed_reads`` reads after
  trimming (fastq_fastqc_umitools_trimgalore getTrimGaloreReadsAfterFiltering,
  float32 as Groovy's ``toFloat()``), plus ``library=<run minus _T<n>>``;
- ``libraries/<lib>``: one per library, ``runs=<run ids>`` (the
  PICARD_MERGESAMFILES_LIBRARY groupTuple on ``id - ~/_T\\d+$/``);
- ``replicates/<rep>``: one per sample with more than one library,
  ``libraries=<library ids>`` (the PICARD_MERGESAMFILES_REPLICATE groupTuple
  on ``id - ~/_REP\\d+$/`` and its ``bams.size() > 1`` filter).

``trim-item`` and ``groups`` split the same step for workflow.chained.yaml:
``trim-item`` filters one run of a chained map (its slot's ``meta.env``; a
dropped run exits 10) and ``groups`` writes the library and replicate lists
from the runs that passed.

Usage: decide.py trimmed --runs DIR --trimgalore DIR --min-trimmed-reads N
       --trim-pass DIR --libraries DIR --replicates DIR
       decide.py trim-item --slot DIR --min-trimmed-reads N --out DIR
       decide.py groups --runs DIR --libraries DIR --replicates DIR
       decide.py --selftest
"""

from __future__ import annotations

import argparse
import re
import shlex
import struct
import sys
import tempfile
from pathlib import Path

TOTAL_RE = re.compile(r"([\d\.]+)\ssequences processed in total")
SHORT_RE = re.compile(r"shorter than the length cutoff[^:]+:\s([\d\.]+)")


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def read_meta(path: Path) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: " ".join(shlex.split(v)) for k, v in pairs}


def write_meta(path: Path, meta: dict[str, str]) -> None:
    """bash-sourceable: values shell-quoted (run and library lists hold spaces)."""
    path.write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in meta.items()))


def reads_after_filtering(log: Path) -> float:
    total = filtered = 0.0
    for line in log.read_text().splitlines():
        if m := TOTAL_RE.search(line):
            total = f32(float(m.group(1)))
        if m := SHORT_RE.search(line):
            filtered = f32(float(m.group(1)))
    return f32(total - filtered)


def trim_log(trimgalore: Path, rid: str, single_end: bool) -> Path | None:
    """The report the filter reads: the only one (SE) or the last, R2 (PE)."""
    name = f"{rid}.fastq.gz_trimming_report.txt" if single_end else f"{rid}_2.fastq.gz_trimming_report.txt"
    found = sorted(trimgalore.glob(f"*/{name}")) + sorted(trimgalore.glob(name))
    return found[0] if found else None


DROP = 10  # drop_exit_codes of the chained filter map


def passes(trimgalore: Path, rid: str, meta: dict[str, str], minimum: float) -> bool:
    log = trim_log(trimgalore, rid, meta["single_end"] == "true")
    return (reads_after_filtering(log) if log else minimum + 1) >= minimum


def trimmed(args: argparse.Namespace) -> None:
    out_runs = Path(args.trim_pass)
    out_runs.mkdir(parents=True, exist_ok=True)
    minimum = f32(float(args.min_trimmed_reads))
    passed = []
    for meta_file in sorted(Path(args.runs).iterdir()):
        rid, meta = meta_file.name, read_meta(meta_file)
        if passes(Path(args.trimgalore), rid, meta, minimum):
            meta = {**meta, "library": re.sub(r"_T\d+$", "", rid)}
            write_meta(out_runs / rid, meta)
            passed.append((rid, meta))
    group(passed, Path(args.libraries), Path(args.replicates))


def trim_item(args: argparse.Namespace) -> None:
    meta = read_meta(Path(args.slot) / "meta.env")
    rid = meta["id"]
    if not passes(Path(args.slot), rid, meta, f32(float(args.min_trimmed_reads))):
        print(f"{rid}: fewer than {args.min_trimmed_reads} reads after trimming", file=sys.stderr)
        sys.exit(DROP)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_meta(out / "meta.env", {**meta, "library": re.sub(r"_T\d+$", "", rid)})


def groups(args: argparse.Namespace) -> None:
    runs = (read_meta(f) for f in Path(args.runs).glob("*/meta.env"))
    passed = sorted(((m.pop("id"), m) for m in runs), key=lambda r: r[0])
    group(passed, Path(args.libraries), Path(args.replicates))


def group(passed: list[tuple[str, dict[str, str]]], out_libs: Path, out_reps: Path) -> None:
    for d in (out_libs, out_reps):
        d.mkdir(parents=True, exist_ok=True)
    libraries: dict[str, dict[str, str]] = {}
    for rid, meta in passed:
        lib = meta.pop("library")
        entry = libraries.setdefault(lib, {**meta, "runs": ""})
        entry["runs"] = f"{entry['runs']} {rid}".strip()
    replicates: dict[str, dict[str, str]] = {}
    for lib, meta in libraries.items():
        write_meta(out_libs / lib, meta)
        rep = re.sub(r"_REP\d+$", "", lib)
        control = re.sub(r"_REP\d+$", "", meta.get("control", ""))
        entry = replicates.setdefault(rep, {"single_end": meta["single_end"], "control": control, "libraries": ""})
        entry["libraries"] = f"{entry['libraries']} {lib}".strip()
    for rep, meta in replicates.items():
        if len(meta["libraries"].split()) > 1:
            write_meta(out_reps / rep, meta)


def selftest() -> None:
    se_log = "1000 sequences processed in total\nSequences removed because they became shorter than the length cutoff of 20 bp:\t10 (1.0%)\n"
    pe_log = "50 sequences processed in total\nshorter than the length cutoff of 20 bp:\t5 (10.0%)\n"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        runs, tg = t / "runs", t / "tg"
        runs.mkdir()
        (tg / "0").mkdir(parents=True)
        for rid, se in (("A_REP1_T1", "false"), ("A_REP1_T2", "false"), ("A_REP2_T1", "false"), ("B_REP1_T1", "true"), ("C_REP1_T1", "true")):
            write_meta(runs / rid, {"single_end": se, "control": ""})
        (tg / "0/A_REP1_T1_2.fastq.gz_trimming_report.txt").write_text(se_log)
        (tg / "0/A_REP2_T1_2.fastq.gz_trimming_report.txt").write_text(se_log)
        (tg / "0/B_REP1_T1.fastq.gz_trimming_report.txt").write_text(se_log)
        (tg / "0/C_REP1_T1.fastq.gz_trimming_report.txt").write_text(pe_log)  # 45 reads: dropped
        ns = argparse.Namespace(runs=runs, trimgalore=tg, min_trimmed_reads="100",
                                trim_pass=t / "p", libraries=t / "l", replicates=t / "r")
        trimmed(ns)
        assert sorted(p.name for p in (t / "p").iterdir()) == ["A_REP1_T1", "A_REP1_T2", "A_REP2_T1", "B_REP1_T1"]
        assert read_meta(t / "p/A_REP1_T2")["library"] == "A_REP1"
        assert read_meta(t / "l/A_REP1")["runs"] == "A_REP1_T1 A_REP1_T2"
        assert sorted(p.name for p in (t / "l").iterdir()) == ["A_REP1", "A_REP2", "B_REP1"]
        assert [p.name for p in (t / "r").iterdir()] == ["A"]
        assert read_meta(t / "r/A") == {"single_end": "false", "control": "", "libraries": "A_REP1 A_REP2"}
        assert "libraries='A_REP1 A_REP2'" in (t / "r/A").read_text()
        assert reads_after_filtering(tg / "0/C_REP1_T1.fastq.gz_trimming_report.txt") == 45.0

        # Chained: the same decisions per slot, then groups from the passing slots.
        for i, rid in enumerate(sorted(p.name for p in runs.iterdir())):
            slot = t / "slots" / str(i)
            slot.mkdir(parents=True)
            (slot / "meta.env").write_text(f"id={rid}\n" + (runs / rid).read_text())
            for rep in tg.glob(f"0/{rid}*_trimming_report.txt"):
                (slot / rep.name).write_text(rep.read_text())
            try:
                trim_item(argparse.Namespace(slot=slot, min_trimmed_reads="100", out=t / "ft" / str(i)))
            except SystemExit as e:
                assert e.code == DROP and rid == "C_REP1_T1", (rid, e.code)
        assert read_meta(t / "ft/1/meta.env") == {"id": "A_REP1_T2", **read_meta(t / "p/A_REP1_T2")}
        groups(argparse.Namespace(runs=t / "ft", libraries=t / "l2", replicates=t / "r2"))
        for d in ("l", "r"):
            got = {p.name: p.read_text() for p in (t / f"{d}2").iterdir()}
            assert got == {p.name: p.read_text() for p in (t / d).iterdir()}, d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("trimmed")
    t.add_argument("--runs", required=True)
    t.add_argument("--trimgalore", required=True)
    t.add_argument("--min-trimmed-reads", dest="min_trimmed_reads", required=True)
    t.add_argument("--trim-pass", dest="trim_pass", required=True)
    t.add_argument("--libraries", required=True)
    t.add_argument("--replicates", required=True)
    ti = sub.add_parser("trim-item")
    ti.add_argument("--slot", required=True)
    ti.add_argument("--min-trimmed-reads", dest="min_trimmed_reads", required=True)
    ti.add_argument("--out", required=True)
    g = sub.add_parser("groups")
    g.add_argument("--runs", required=True)
    g.add_argument("--libraries", required=True)
    g.add_argument("--replicates", required=True)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return 0
    cmds = {"trimmed": trimmed, "trim-item": trim_item, "groups": groups}
    if args.cmd not in cmds:
        ap.error("pick trimmed, trim-item, groups or --selftest")
    cmds[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
