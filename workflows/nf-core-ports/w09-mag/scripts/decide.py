#!/usr/bin/env python3
"""
nf-core/mag's Groovy-side channel logic after binning, as tasks.

Each list it writes is a folder of item folders, one per Nextflow task of the
next step, named by that task's prefix and holding copies of its bins plus a
bash-sourceable ``meta.env`` (assembler, binner, id, refinement).

``binsets``      MetaBAT2 / MaxBin2 / SemiBin2 outputs -> ``binsets/<ASM>-<BINNER>-<id>``
                 (bins, for SEQKIT_STATS) and ``unbinsets/`` (unbinned contigs, for
                 SPLIT_FASTA), as BINNING emits them.
``postbinning``  SEQKIT_STATS bin size filter (--bin_min_size/--bin_max_size) and
                 SPLIT_FASTA outputs -> the post-binning sets (bins and unbinned,
                 ``<ASM>-<BINNER>-unclassified-<refinement>-<id>``), their bins and
                 unbinned subsets, one folder per bin (PROKKA), the MAG_DEPTHS groups
                 and contig_to_bin_map.tsv.
``gtdb``         BUSCO completeness / duplication per bin -> the sets GTDB-Tk
                 classifies (passing bins) and the discarded bin names.

stdlib only. Usage: decide.py <step> --help, or decide.py --selftest.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import gzip
import re
import shutil
import sys
import tempfile
from pathlib import Path

# BINNING emits MetaBAT2 bins with this Nextflow glob (a character class).
METABAT2_BINS = "*[!lowDepth|tooShort|unbinned].fa.gz"


def read_meta(path: Path) -> dict[str, str]:
    return dict(re.findall(r"^(\w+)='([^']*)'$", path.read_text(), re.M))


def fresh(folder: Path) -> Path:
    """An empty output folder: a forced rerun must not find the last run's sets."""
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    return folder


def write_set(folder: Path, files: list[Path], meta: dict[str, str]) -> None:
    folder.mkdir(parents=True)
    for f in files:
        shutil.copyfile(f, folder / f.name)
    (folder / "meta.env").write_text("".join(f"{k}='{v}'\n" for k, v in meta.items()))


def bin_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.name != "meta.env")


def find(root: Path, pattern: str) -> list[Path]:
    """Files matching *pattern* (a name glob) in any map slot under *root*."""
    return sorted(p for p in root.glob("*/" + pattern) if p.is_file())


# -- binsets ------------------------------------------------------------------


def binsets(args: argparse.Namespace) -> None:
    out_bins, out_unbins = Path(args.binsets), Path(args.unbinsets)
    fresh(out_bins), fresh(out_unbins)
    for a in sorted(Path(args.assemblies).iterdir()):
        m = read_meta(a)
        asm, sid = m["assembler"], m["id"]
        for binner in ("MetaBAT2", "MaxBin2", "SemiBin2"):
            prefix = f"{asm}-{binner}-{sid}"
            meta = {"assembler": asm, "binner": binner, "id": sid}
            if binner == "MetaBAT2":
                bins = [p for p in find(Path(args.metabat2), f"{prefix}.*.fa.gz") if fnmatch.fnmatchcase(p.name, METABAT2_BINS)]
                unbinned = find(Path(args.metabat2), f"{prefix}.unbinned.fa.gz")
            elif binner == "MaxBin2":
                bins = find(Path(args.maxbin2), f"{prefix}.*.fa.gz")
                unbinned = find(Path(args.maxbin2), f"{prefix}.noclass.gz")
            else:
                bins = find(Path(args.semibin), f"bins/{prefix}*.fa.gz")
                unbinned = []
            if bins:
                write_set(out_bins / prefix, bins, meta)
            if unbinned:
                write_set(out_unbins / prefix, unbinned, meta)


# -- postbinning --------------------------------------------------------------


def seqkit_lengths(path: Path) -> dict[str, int]:
    with open(path, newline="") as fh:
        return {r["file"].strip(): int(r["sum_len"].strip()) for r in csv.DictReader(fh, delimiter="\t")}


def fasta_headers(path: Path) -> list[str]:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt") as fh:
        return [line[1:].rstrip("\n") for line in fh if line.startswith(">")]


def postbinning(args: argparse.Namespace) -> None:
    lo, hi = args.bin_min_size, args.bin_max_size  # hi 0 = no maximum
    keep = lambda n: n >= lo and (not hi or n <= hi)  # noqa: E731
    sets = []  # (name, files, meta)
    n_bins = n_kept = 0
    for d in sorted(Path(args.binsets).iterdir()):
        m = read_meta(d / "meta.env")
        prefix = d.name
        lengths = {}
        for f in find(Path(args.seqkit), f"{prefix}.tsv"):
            lengths.update(seqkit_lengths(f))
        bins = bin_files(d)
        kept = [b for b in bins if keep(lengths[b.name])]
        n_bins, n_kept = n_bins + len(bins), n_kept + len(kept)
        if kept:
            sets.append((f"{m['assembler']}-{m['binner']}-unclassified-unrefined-{m['id']}", kept, {**m, "refinement": "unrefined"}))
    if n_bins and not n_kept:
        raise SystemExit(
            f"[nf-core/mag] ERROR: no bins passed the bin size filter specified between --bin_min_size {lo} and --bin_max_size {hi or None}. Please adjust parameters."
        )
    for d in sorted(Path(args.unbinsets).iterdir()):
        m = read_meta(d / "meta.env")
        # SPLIT_FASTA's `unbinned` output glob
        files = find(Path(args.split_fasta), f"{d.name}.*.[1-9]*.fa.gz")
        if files:
            sets.append((f"{m['assembler']}-{m['binner']}-unclassified-unrefined_unbinned-{m['id']}", files, {**m, "refinement": "unrefined_unbinned"}))

    out = {k: Path(getattr(args, k)) for k in ("post", "post_bins", "post_unbins", "bins", "depthsets")}
    for d in out.values():
        fresh(d)
    groups: dict[str, tuple[list[Path], dict[str, str]]] = {}
    rows = []
    for name, files, meta in sets:
        write_set(out["post"] / name, files, meta)
        write_set(out["post_bins" if meta["refinement"] == "unrefined" else "post_unbins"] / name, files, meta)
        prefix = f"{meta['assembler']}-{meta['binner']}-{meta['id']}"
        g = groups.setdefault(prefix, ([], {k: meta[k] for k in ("assembler", "binner", "id")}))
        g[0].extend(files)
        for f in files:
            bin_id = re.sub(r"\.fa(sta)?(\.gz)?$", "", f.name)
            write_set(out["bins"] / bin_id, [f], {**meta, "bin_id": bin_id})
            for header in fasta_headers(f):
                rows.append(f"{meta['assembler']}-{meta['id']}\t{header}\t{meta['binner']}\t{f.name.removesuffix('.gz')}\n")
    for prefix, (files, meta) in groups.items():
        write_set(out["depthsets"] / prefix, sorted(set(files), key=lambda p: p.name), meta)
    # collectFile(keepHeader: true, sort: true): one header, then the sorted rows
    Path(args.contig_map).parent.mkdir(parents=True, exist_ok=True)
    Path(args.contig_map).write_text("assembly_id\tcontig_id\tbinner\tbin_id\n" + "".join(sorted(rows)))


# -- gtdb ---------------------------------------------------------------------


def gtdb(args: argparse.Namespace) -> None:
    # BUSCO batch summaries: Input_file, Complete (completeness), Duplicated (contamination)
    metrics: dict[str, list[tuple[float, float]]] = {}
    for f in find(Path(args.busco), "*-busco.batch_summary.txt"):
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                readings = metrics.setdefault(row["Input_file"], [])
                comp, cont = float(row["Complete"]), float(row["Duplicated"])
                if comp >= 0 and cont >= 0:
                    readings.append((comp, cont))
    out = fresh(Path(args.out))
    discarded = []
    for d in sorted(Path(args.post).iterdir()):
        passed = []
        for b in bin_files(d):
            readings = metrics.get(b.name.removesuffix(".gz"))
            if readings is None:
                continue
            if any(c >= args.min_completeness and x <= args.max_contamination for c, x in readings):
                passed.append(b)
            else:
                discarded.append(b.name)
        if passed:
            write_set(out / d.name, passed, read_meta(d / "meta.env"))
    Path(args.discarded).parent.mkdir(parents=True, exist_ok=True)
    Path(args.discarded).write_text("".join(f"{n}\n" for n in discarded))


# -- selftest -----------------------------------------------------------------


def _fa(path: Path, *records: tuple[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.writelines(f">{h}\n{s}\n" for h, s in records)
    return path


def selftest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "asm").mkdir()
        (t / "asm/MEGAHIT-a").write_text("assembler='MEGAHIT'\nid='a'\ngroup='0'\next='contigs'\n")
        _fa(t / "mb/0/MEGAHIT-MetaBAT2-a.1.fa.gz", ("c1", "ACGT"))
        _fa(t / "mb/0/MEGAHIT-MetaBAT2-a.unbinned.fa.gz", ("c9", "A"))
        _fa(t / "mb/0/MEGAHIT-MetaBAT2-a.tooShort.fa.gz", ("c8", "A"))
        _fa(t / "mx/0/MEGAHIT-MaxBin2-a.001.fa.gz", ("c2", "ACG"))
        (t / "sb/0/bins").mkdir(parents=True)
        ns = argparse.Namespace(assemblies=t / "asm", metabat2=t / "mb", maxbin2=t / "mx", semibin=t / "sb", binsets=t / "bs", unbinsets=t / "us")
        binsets(ns)
        binsets(ns)  # a forced rerun writes into the last run's folder
        assert sorted(p.name for p in (t / "bs").iterdir()) == ["MEGAHIT-MaxBin2-a", "MEGAHIT-MetaBAT2-a"]
        assert [p.name for p in bin_files(t / "bs/MEGAHIT-MetaBAT2-a")] == ["MEGAHIT-MetaBAT2-a.1.fa.gz"]
        assert [p.name for p in (t / "us").iterdir()] == ["MEGAHIT-MetaBAT2-a"]
        (t / "sk/0").mkdir(parents=True)
        (t / "sk/0/MEGAHIT-MetaBAT2-a.tsv").write_text("file\tsum_len\nMEGAHIT-MetaBAT2-a.1.fa.gz\t4\n")
        (t / "sk/1").mkdir(parents=True)
        (t / "sk/1/MEGAHIT-MaxBin2-a.tsv").write_text("file\tsum_len\nMEGAHIT-MaxBin2-a.001.fa.gz\t3\n")
        _fa(t / "sf/0/MEGAHIT-MetaBAT2-a.unbinned.1.fa.gz", ("c9", "A"))
        _fa(t / "sf/0/MEGAHIT-MetaBAT2-a.unbinned.pooled.fa.gz", ("c7", "A"))
        dirs = {k: t / k for k in ("post", "post_bins", "post_unbins", "bins", "depthsets")}
        ns = argparse.Namespace(binsets=t / "bs", unbinsets=t / "us", seqkit=t / "sk", split_fasta=t / "sf", bin_min_size=4, bin_max_size=0, contig_map=t / "c2b.tsv", **dirs)
        postbinning(ns)
        assert sorted(p.name for p in (t / "post").iterdir()) == [
            "MEGAHIT-MetaBAT2-unclassified-unrefined-a",
            "MEGAHIT-MetaBAT2-unclassified-unrefined_unbinned-a",
        ], "MaxBin2 bin under --bin_min_size must be dropped"
        assert sorted(p.name for p in (t / "bins").iterdir()) == ["MEGAHIT-MetaBAT2-a.1", "MEGAHIT-MetaBAT2-a.unbinned.1"]
        assert [p.name for p in bin_files(t / "depthsets/MEGAHIT-MetaBAT2-a")] == ["MEGAHIT-MetaBAT2-a.1.fa.gz", "MEGAHIT-MetaBAT2-a.unbinned.1.fa.gz"]
        assert (t / "c2b.tsv").read_text().splitlines()[1] == "MEGAHIT-a\tc1\tMetaBAT2\tMEGAHIT-MetaBAT2-a.1.fa"
        try:
            postbinning(argparse.Namespace(**{**vars(ns), "bin_min_size": 10, **{k: t / f"x{k}" for k in dirs}}))
            raise AssertionError("no bin passing the size filter must fail")
        except SystemExit:
            pass
        (t / "bu/0").mkdir(parents=True)
        (t / "bu/0/a-x-busco.batch_summary.txt").write_text(
            "Input_file\tComplete\tDuplicated\nMEGAHIT-MetaBAT2-a.1.fa\t19.4\t0.0\nMEGAHIT-MetaBAT2-a.unbinned.1.fa\t0.0\t0.0\n"
        )
        gtdb(argparse.Namespace(busco=t / "bu", post=t / "post", out=t / "gt", discarded=t / "disc.txt", min_completeness=0.01, max_contamination=10.0))
        assert [p.name for p in (t / "gt").iterdir()] == ["MEGAHIT-MetaBAT2-unclassified-unrefined-a"]
        assert (t / "disc.txt").read_text() == "MEGAHIT-MetaBAT2-a.unbinned.1.fa.gz\n"
    sys.stderr.write("selftest ok\n")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("binsets")
    for k in ("assemblies", "metabat2", "maxbin2", "semibin", "binsets", "unbinsets"):
        s.add_argument(f"--{k}", required=True)
    s.set_defaults(fn=binsets)
    s = sub.add_parser("postbinning")
    for k in ("binsets", "unbinsets", "seqkit", "split-fasta", "post", "post-bins", "post-unbins", "bins", "depthsets", "contig-map"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--bin-min-size", type=int, default=0)
    s.add_argument("--bin-max-size", type=int, default=0, help="0: no maximum")
    s.set_defaults(fn=postbinning)
    s = sub.add_parser("gtdb")
    for k in ("busco", "post", "out", "discarded"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--min-completeness", type=float, required=True)
    s.add_argument("--max-contamination", type=float, required=True)
    s.set_defaults(fn=gtdb)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
