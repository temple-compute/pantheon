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

workflow.chained.yaml streams the post-binning steps per set instead:

``sets``         as ``binsets``, but bins and unbinned contigs in one folder of
                 items named by their post-binning set, so one map chain runs both.
``post-item``    one item (a map clone): the bin size filter on its SeqKit stats, or
                 its SPLIT_FASTA files -> the post-binning set; exit 10 when empty.
``post-sets``    all post-binning sets -> PROKKA bins, MAG_DEPTHS groups and
                 contig_to_bin_map.tsv (these join sets, so they stay a task).
``gtdb-item``    one BUSCO item -> its bins that GTDB-Tk classifies; exit 10 when none.

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
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copyfile(f, folder / f.name)
    (folder / "meta.env").write_text("".join(f"{k}='{v}'\n" for k, v in meta.items()))


def bin_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.name != "meta.env")


def find(root: Path, pattern: str) -> list[Path]:
    """Files matching *pattern* (a name glob) in any map slot under *root*."""
    return sorted(p for p in root.glob("*/" + pattern) if p.is_file())


# -- binsets ------------------------------------------------------------------


def binner_sets(args: argparse.Namespace):
    """(prefix, meta, bins, unbinned) per assembly and binner, as BINNING emits them."""
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
            yield prefix, meta, bins, unbinned


def binsets(args: argparse.Namespace) -> None:
    out_bins, out_unbins = Path(args.binsets), Path(args.unbinsets)
    fresh(out_bins), fresh(out_unbins)
    for prefix, meta, bins, unbinned in binner_sets(args):
        if bins:
            write_set(out_bins / prefix, bins, meta)
        if unbinned:
            write_set(out_unbins / prefix, unbinned, meta)


def set_name(meta: dict[str, str], refinement: str) -> str:
    return f"{meta['assembler']}-{meta['binner']}-unclassified-{refinement}-{meta['id']}"


def sets(args: argparse.Namespace) -> None:
    out = fresh(Path(args.sets))
    for _prefix, meta, bins, unbinned in binner_sets(args):
        for files, refinement in ((bins, "unrefined"), (unbinned, "unrefined_unbinned")):
            if files:
                name = set_name(meta, refinement)
                write_set(out / name, files, {**meta, "refinement": refinement, "name": name})


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
            sets.append((set_name(m, "unrefined"), kept, {**m, "refinement": "unrefined"}))
    if n_bins and not n_kept:
        no_bins_passed(lo, hi)
    for d in sorted(Path(args.unbinsets).iterdir()):
        m = read_meta(d / "meta.env")
        # SPLIT_FASTA's `unbinned` output glob
        files = find(Path(args.split_fasta), f"{d.name}.*.[1-9]*.fa.gz")
        if files:
            sets.append((set_name(m, "unrefined_unbinned"), files, {**m, "refinement": "unrefined_unbinned"}))
    write_post(args, sets, ("post", "post_bins", "post_unbins"))


def no_bins_passed(lo: int, hi: int) -> None:
    raise SystemExit(
        f"[nf-core/mag] ERROR: no bins passed the bin size filter specified between --bin_min_size {lo} and --bin_max_size {hi or None}. Please adjust parameters."
    )


def write_post(args: argparse.Namespace, sets: list, set_dirs: tuple[str, ...]) -> None:
    """The set lists in *set_dirs*, the per-bin and depth group lists and contig_to_bin_map.tsv."""
    out = {k: Path(getattr(args, k)) for k in (*set_dirs, "bins", "depthsets")}
    for d in out.values():
        fresh(d)
    groups: dict[str, tuple[list[Path], dict[str, str]]] = {}
    rows = []
    for name, files, meta in sets:
        if set_dirs:
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


DROP = 10  # map clone exit code for a dropped item (drop_exit_codes)


def post_item(args: argparse.Namespace) -> None:
    """One sets item: its post-binning set in --out, or exit 10 when nothing passes."""
    m = read_meta(Path(args.slot) / "meta.env")
    prefix = f"{m['assembler']}-{m['binner']}-{m['id']}"
    if m["refinement"] == "unrefined":
        lengths = seqkit_lengths(Path(args.slot) / f"{prefix}.tsv")
        lo, hi = args.bin_min_size, args.bin_max_size
        files = [b for b in bin_files(Path(args.sets) / m["name"]) if lengths[b.name] >= lo and (not hi or lengths[b.name] <= hi)]
    else:
        files = sorted(Path(args.split).glob(f"{prefix}.*.[1-9]*.fa.gz"))  # SPLIT_FASTA's `unbinned` output glob
    if not files:
        sys.exit(DROP)
    out = fresh(Path(args.out))
    write_set(out, files, m)


def post_sets(args: argparse.Namespace) -> list:
    """The post-binning sets in name order: named folders (postbinning) or the post-item map's
    numbered slots (dropped slots have no meta.env)."""
    found = []
    for d in Path(args.post).glob("*/"):  # no folder at all when every item dropped
        if (d / "meta.env").is_file():
            m = read_meta(d / "meta.env")
            found.append((m.get("name", d.name), bin_files(d), m))
    return sorted(found, key=lambda s: s[0])


def post_sets_cmd(args: argparse.Namespace) -> None:
    sets_ = post_sets(args)
    has_bins = any(read_meta(d / "meta.env")["refinement"] == "unrefined" for d in Path(args.sets).iterdir())
    if has_bins and not any(m["refinement"] == "unrefined" for _n, _f, m in sets_):
        no_bins_passed(args.bin_min_size, args.bin_max_size)
    write_post(args, sets_, ())


# -- gtdb ---------------------------------------------------------------------


def busco_metrics(files: list[Path]) -> dict[str, list[tuple[float, float]]]:
    """BUSCO batch summaries: Input_file -> (Complete, Duplicated) readings, negative ones left out."""
    metrics: dict[str, list[tuple[float, float]]] = {}
    for f in files:
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                readings = metrics.setdefault(row["Input_file"], [])
                comp, cont = float(row["Complete"]), float(row["Duplicated"])
                if comp >= 0 and cont >= 0:
                    readings.append((comp, cont))
    return metrics


def gtdb_split(args: argparse.Namespace, metrics: dict, bins: list[Path]) -> tuple[list[Path], list[str]]:
    """(passed, discarded); a bin without a BUSCO row is in neither."""
    passed, discarded = [], []
    for b in bins:
        readings = metrics.get(b.name.removesuffix(".gz"))
        if readings is None:
            continue
        if any(c >= args.min_completeness and x <= args.max_contamination for c, x in readings):
            passed.append(b)
        else:
            discarded.append(b.name)
    return passed, discarded


def gtdb(args: argparse.Namespace) -> None:
    metrics = busco_metrics(find(Path(args.busco), "*-busco.batch_summary.txt"))
    out = fresh(Path(args.out)) if args.out else None
    discarded = []
    # chained: post is the post-item map output (numbered slots), so go by set name
    for name, files, meta in post_sets(args):
        passed, dropped = gtdb_split(args, metrics, files)
        discarded += dropped
        if passed and out:
            write_set(out / name, passed, meta)
    Path(args.discarded).parent.mkdir(parents=True, exist_ok=True)
    Path(args.discarded).write_text("".join(f"{n}\n" for n in discarded))


def gtdb_item(args: argparse.Namespace) -> None:
    """One BUSCO item: the set's bins GTDB-Tk classifies in --out, or exit 10 when none pass."""
    passed, _ = gtdb_split(args, busco_metrics(sorted(Path(args.busco).glob("*-busco.batch_summary.txt"))), bin_files(Path(args.set)))
    if not passed:
        sys.exit(DROP)
    write_set(fresh(Path(args.out)), passed, read_meta(Path(args.set) / "meta.env"))


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

        # chained: sets -> post-item per slot -> post-sets, gtdb-item, gtdb (discarded only)
        ns = argparse.Namespace(assemblies=t / "asm", metabat2=t / "mb", maxbin2=t / "mx", semibin=t / "sb", sets=t / "sets")
        sets(ns)
        names = sorted(p.name for p in (t / "sets").iterdir())
        assert names == [
            "MEGAHIT-MaxBin2-unclassified-unrefined-a",
            "MEGAHIT-MetaBAT2-unclassified-unrefined-a",
            "MEGAHIT-MetaBAT2-unclassified-unrefined_unbinned-a",
        ], names
        drops = []
        for i, name in enumerate(names):  # seqkit slots carry the item's meta.env and stats
            slot = t / f"skc/{i}"
            slot.mkdir(parents=True)
            shutil.copyfile(t / "sets" / name / "meta.env", slot / "meta.env")
            prefix = name.replace("-unclassified-unrefined_unbinned", "").replace("-unclassified-unrefined", "")
            for f in (t / "sk").glob(f"*/{prefix}.tsv"):
                shutil.copyfile(f, slot / f.name)
            try:
                post_item(argparse.Namespace(slot=slot, split=t / "sf/0", sets=t / "sets", out=t / f"pf/{i}", bin_min_size=4, bin_max_size=0))
            except SystemExit as e:
                assert e.code == DROP
                drops.append(name)
        assert drops == ["MEGAHIT-MaxBin2-unclassified-unrefined-a"], drops
        assert [p.name for p in bin_files(t / "pf/2")] == ["MEGAHIT-MetaBAT2-a.unbinned.1.fa.gz"]
        cdirs = {k: t / f"c{k}" for k in ("bins", "depthsets")}
        post_sets_cmd(argparse.Namespace(post=t / "pf", sets=t / "sets", contig_map=t / "cc2b.tsv", bin_min_size=4, bin_max_size=0, **cdirs))
        assert sorted(p.name for p in (t / "cbins").iterdir()) == ["MEGAHIT-MetaBAT2-a.1", "MEGAHIT-MetaBAT2-a.unbinned.1"]
        assert (t / "cc2b.tsv").read_text() == (t / "c2b.tsv").read_text()
        post_sets_cmd(argparse.Namespace(post=t / "pf", sets=t / "sets", contig_map=t / "cc2b.tsv", bin_min_size=4, bin_max_size=0, **cdirs))  # rerun
        try:
            post_sets_cmd(argparse.Namespace(post=t / "nothing", sets=t / "sets", contig_map=t / "x.tsv", bin_min_size=10, bin_max_size=0, **cdirs))
            raise AssertionError("no bin passing the size filter must fail")
        except SystemExit as e:
            assert e.code != DROP
        g = dict(min_completeness=0.01, max_contamination=10.0)
        gtdb_item(argparse.Namespace(busco=t / "bu/0", set=t / "pf/1", out=t / "gi/1", **g))
        assert [p.name for p in bin_files(t / "gi/1")] == ["MEGAHIT-MetaBAT2-a.1.fa.gz"]
        try:
            gtdb_item(argparse.Namespace(busco=t / "bu/0", set=t / "pf/2", out=t / "gi/2", **g))
            raise AssertionError("a set with no passing bin must drop")
        except SystemExit as e:
            assert e.code == DROP
        gtdb(argparse.Namespace(busco=t / "bu", post=t / "pf", out=None, discarded=t / "cdisc.txt", **g))
        assert (t / "cdisc.txt").read_text() == (t / "disc.txt").read_text()
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
    for k in ("busco", "post", "discarded"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--out", help="also write the passing sets here")
    s.add_argument("--min-completeness", type=float, required=True)
    s.add_argument("--max-contamination", type=float, required=True)
    s.set_defaults(fn=gtdb)
    s = sub.add_parser("sets")
    for k in ("assemblies", "metabat2", "maxbin2", "semibin", "sets"):
        s.add_argument(f"--{k}", required=True)
    s.set_defaults(fn=sets)
    s = sub.add_parser("post-item")
    for k in ("slot", "split", "sets", "out"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--bin-min-size", type=int, default=0)
    s.add_argument("--bin-max-size", type=int, default=0, help="0: no maximum")
    s.set_defaults(fn=post_item)
    s = sub.add_parser("post-sets")
    for k in ("post", "sets", "bins", "depthsets", "contig-map"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--bin-min-size", type=int, default=0)
    s.add_argument("--bin-max-size", type=int, default=0)
    s.set_defaults(fn=post_sets_cmd)
    s = sub.add_parser("gtdb-item")
    for k in ("busco", "set", "out"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--min-completeness", type=float, required=True)
    s.add_argument("--max-contamination", type=float, required=True)
    s.set_defaults(fn=gtdb_item)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
