#!/usr/bin/env python3
"""
The Groovy-side decisions of nf-core/rnaseq 3.27.0, as small file-in/file-out steps.

Each subcommand reads per-sample meta files (bash-sourceable ``key=value``,
one file per sample, named by sample id) and tool outputs, and writes the
next list of meta files. A ``horus_map`` over that list then runs only the
samples that passed, which is what the pipeline's channel ``filter``/``branch``
calls do.

- ``trimmed``: min_trimmed_reads filter on the TrimGalore reports
  (fastq_fastqc_umitools_trimgalore getTrimGaloreReadsAfterFiltering), and
  the ``auto`` strandedness branch.
- ``strandedness``: Salmon lib_format_counts.json -> forward / reverse /
  unstranded (fastq_qc_trim_filter_setstrandedness getSalmonInferredStrandedness).
- ``mapped``: min_mapped_reads filter on STAR Log.final.out (align_star
  getStarPercentMapped), and the stranded subset for the per-strand bigWigs.
- ``multiqc``: name_replacement.txt, multiqc_sample_merge.yml, the
  strandedness check sections and the fail_* tables (multiqc_rnaseq,
  utils_nfcore_rnaseq_pipeline). Needs PyYAML (run it in the MultiQC image).
- ``trim-item``, ``strand-item``, ``map-item``: the same three decisions for
  one sample of a chained map (workflow.chained.yaml). They read and write a
  ``meta.env`` in the map slot; a dropped sample exits 10 (DROP).

Numbers that Groovy parses with ``toFloat()`` are rounded to float32 here too,
and printed the way Java prints a Float, so the tables match byte for byte.

Usage: decide.py <subcommand> --help, or decide.py --selftest
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import re
import struct
import sys
import tempfile
from pathlib import Path

# -- helpers ------------------------------------------------------------------


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def java_float_str(x: float) -> str:
    """Float.toString for a float32 value (shortest round-trip digits)."""
    v = f32(x)
    if v == 0:
        return "0.0"
    for digits in range(1, 10):
        s = f"{v:.{digits}g}"
        if f32(float(s)) == v:
            break
    m = float(s)
    if 1e-3 <= abs(m) < 1e7:
        return repr(m)
    mant, exp = f"{m:.{digits - 1}e}".split("e")
    mant = mant if "." in mant else mant + ".0"
    return f"{mant}E{int(exp)}"


def read_meta(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def write_meta(path: Path, meta: dict[str, str]) -> None:
    path.write_text("".join(f"{k}={v}\n" for k, v in meta.items()))


def metas(folder: str) -> list[tuple[str, dict[str, str]]]:
    """(sample id, meta) per sample: files named by id, or map slots holding meta.env (keyed by id)."""
    slots = sorted(Path(folder).glob("*/meta.env"))
    if slots:
        return sorted(((m["id"], m) for m in map(read_meta, slots)), key=lambda t: t[0])
    return [(p.name, read_meta(p)) for p in sorted(Path(folder).iterdir()) if p.is_file()]


DROP = 10  # exit code the chained filter maps list in drop_exit_codes


def find_one(root: str, name: str) -> Path | None:
    """The file *name* anywhere under the map output *root* (slot folders, fused stage folders)."""
    hits = sorted(Path(root).glob(f"**/{name}"))
    return hits[0] if hits else None


def calculate_strandedness(fwd: float, rev: float, unstr: float, stranded_t: float, unstranded_t: float) -> dict:
    total = fwd + rev + unstr
    stranded = fwd + rev
    s = "undetermined"
    if stranded > 0:
        fp, rp = fwd / stranded, rev / stranded
        if fp >= stranded_t:
            s = "forward"
        elif rp >= stranded_t:
            s = "reverse"
        elif abs(fp - rp) <= unstranded_t:
            s = "unstranded"
    pct = (lambda v: v / total * 100) if total else (lambda v: math.nan)
    return {"inferred_strandedness": s, "forwardFragments": pct(fwd), "reverseFragments": pct(rev),
            "unstrandedFragments": pct(unstr)}


# -- trimmed ------------------------------------------------------------------


def trimgalore_reads_after_filtering(log: Path) -> float:
    total = filtered = 0.0
    for line in log.read_text().splitlines():
        m = re.search(r"([\d\.]+)\ssequences processed in total", line)
        if m:
            total = f32(float(m.group(1)))
        m = re.search(r"shorter than the length cutoff[^:]+:\s*([\d\.]+)", line)
        if m:
            filtered = f32(float(m.group(1)))
    return f32(total - filtered)


def trimmed_reads(sid: str, meta: dict[str, str], trimgalore: str) -> float | None:
    """Reads left after trimming, from the R2 (or SE) TrimGalore report; None without a report."""
    names = ([f"{sid}_trimmed.fastq.gz_trimming_report.txt"] if meta["single_end"] == "true" else
             [f"{sid}_trimmed_1.fastq.gz_trimming_report.txt", f"{sid}_trimmed_2.fastq.gz_trimming_report.txt"])
    log = find_one(trimgalore, names[-1])  # PE: the R2 report, trim_log[-1]
    return trimgalore_reads_after_filtering(log) if log else None


def fail_trimmed_tsv(fails: list[str]) -> str:
    return "Sample\tReads after trimming\n" + "".join(f + "\n" for f in fails)


def trimmed_fails(samples: list[tuple[str, dict[str, str]]], trimgalore: str, min_reads: float) -> list[str]:
    """fail_trimmed rows: n <= min, while the pass test is n >= min (the pipeline's quirk)."""
    rows = []
    for sid, meta in samples:
        n = trimmed_reads(sid, meta, trimgalore)
        if n is not None and n <= float(min_reads):
            rows.append(f"{sid}\t{java_float_str(n)}")
    return rows


def cmd_trimmed(a: argparse.Namespace) -> None:
    out_pass, out_auto, out_status = (Path(p) for p in (a.passed, a.auto, a.status))
    for d in (out_pass, out_auto, out_status):
        d.mkdir(parents=True, exist_ok=True)
    counts = []
    samples = metas(a.samples)
    for sid, meta in samples:
        n = trimmed_reads(sid, meta, a.trimgalore)
        n = float(a.min_trimmed_reads) + 1 if n is None else n
        counts.append(f"{sid}\t{java_float_str(n)}")
        if n >= float(a.min_trimmed_reads):
            write_meta(out_pass / sid, meta)
            if meta["strandedness"] == "auto":
                write_meta(out_auto / sid, meta)
    (out_status / "trimmed_reads.tsv").write_text("".join(c + "\n" for c in counts))
    fails = trimmed_fails(samples, a.trimgalore, a.min_trimmed_reads)
    if fails:
        (out_status / "fail_trimmed_samples_mqc.tsv").write_text(fail_trimmed_tsv(fails))


def slot_meta(slot: str) -> dict[str, str]:
    return read_meta(Path(slot) / "meta.env")


def write_slot(out: str, meta: dict[str, str]) -> None:
    Path(out).mkdir(parents=True, exist_ok=True)
    write_meta(Path(out) / "meta.env", meta)


def cmd_trim_item(a: argparse.Namespace) -> None:
    meta = slot_meta(a.slot)
    n = trimmed_reads(meta["id"], meta, a.slot)
    if n is not None and not n >= float(a.min_trimmed_reads):
        print(f"{meta['id']}: {java_float_str(n)} reads after trimming, under {a.min_trimmed_reads:g}", file=sys.stderr)
        sys.exit(DROP)
    write_slot(a.out, meta)


# -- strandedness ---------------------------------------------------------------


def salmon_inferred_strandedness(path: Path, stranded_t: float, unstranded_t: float) -> dict:
    lib = json.loads(path.read_text())
    unstr = sum(lib.get(k) or 0 for k in ("IU", "U", "MU"))
    n = float(lib.get("num_assigned_fragments") or 0)
    bias = float(lib.get("strand_mapping_bias") or 0.0)
    return calculate_strandedness(bias * n, (1 - bias) * n, unstr, stranded_t, unstranded_t)


def resolve_strandedness(sid: str, meta: dict[str, str], salmon: str, a: argparse.Namespace) -> dict[str, str]:
    meta = dict(meta, provided=meta["strandedness"])
    if meta["strandedness"] == "auto":
        js = find_one(salmon, f"{sid}_lib_format_counts.json")
        if js is None:
            sys.exit(f"Salmon failed to produce lib_format_counts for sample '{sid}' which was set to 'auto'"
                     " strandedness. Check that the Salmon index matches your input reads, or set"
                     " strandedness explicitly in the samplesheet.")
        r = salmon_inferred_strandedness(js, a.stranded_threshold, a.unstranded_threshold)
        s = r["inferred_strandedness"]
        meta["strandedness"] = "unstranded" if s == "undetermined" else s
        meta.update(salmon_inferred=s, salmon_fwd=repr(r["forwardFragments"]),
                    salmon_rev=repr(r["reverseFragments"]), salmon_unstr=repr(r["unstrandedFragments"]))
    return meta


def cmd_strandedness(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for sid, meta in metas(a.samples):
        write_meta(out / sid, resolve_strandedness(sid, meta, a.salmon, a))


def cmd_strand_item(a: argparse.Namespace) -> None:
    meta = slot_meta(a.slot)
    write_slot(a.out, resolve_strandedness(meta["id"], meta, a.slot, a))


# -- mapped -------------------------------------------------------------------


def star_percent_mapped(log: Path) -> float:
    pct = 0.0
    for line in log.read_text().splitlines():
        m = re.search(r"Uniquely mapped reads %\s*\|\s*([\d\.]+)%", line)
        if m:
            pct = f32(float(m.group(1)))
    return pct


def percent_mapped(sid: str, star: str) -> float | None:
    log = find_one(star, f"{sid}.Log.final.out")
    return star_percent_mapped(log) if log else None


def mapped_ok(pm: float | None, min_mapped: float) -> bool:
    return pm is None or pm >= f32(float(min_mapped))


def mapped_fails(samples: list[tuple[str, dict[str, str]]], star: str, min_mapped: float) -> list[str]:
    rows = []
    for sid, _meta in samples:
        pm = percent_mapped(sid, star)
        if not mapped_ok(pm, min_mapped):
            rows.append(f"{sid}\t{java_float_str(pm)}")
    return rows


def fail_mapped_tsv(header: str, aligner: str, fails: list[str]) -> str:
    return header + f"Sample\t{aligner} (%)\n" + "".join(f + "\n" for f in fails)


def cmd_mapped(a: argparse.Namespace) -> None:
    out_pass, out_stranded, out_status = (Path(p) for p in (a.passed, a.stranded, a.status))
    for d in (out_pass, out_stranded, out_status):
        d.mkdir(parents=True, exist_ok=True)
    rows = []
    samples = metas(a.samples)
    for sid, meta in samples:
        pm = percent_mapped(sid, a.star)
        ok = mapped_ok(pm, a.min_mapped_reads)
        rows.append(f"{sid}\t{'' if pm is None else java_float_str(pm)}\t{'pass' if ok else 'fail'}")
        if ok:
            write_meta(out_pass / sid, meta)
            if meta["strandedness"] in ("forward", "reverse"):
                write_meta(out_stranded / sid, meta)
    (out_status / "percent_mapped.tsv").write_text("".join(r + "\n" for r in rows))
    fails = mapped_fails(samples, a.star, a.min_mapped_reads)
    if fails:
        (out_status / "fail_mapped_samples_mqc.tsv").write_text(
            fail_mapped_tsv(Path(a.status_header).read_text(), a.aligner_display_name, fails))


def cmd_map_item(a: argparse.Namespace) -> None:
    meta = read_meta(Path(a.meta))
    sid = slot_meta(a.slot)["id"]
    if sid != meta["id"]:  # zip pairs slots by name: the item and its strand meta must be one sample
        sys.exit(f"Slot {a.slot} holds sample '{sid}', but {a.meta} is for '{meta['id']}'.")
    pm = percent_mapped(sid, a.star)
    if not mapped_ok(pm, a.min_mapped_reads):
        print(f"{sid}: {java_float_str(pm)}% uniquely mapped, under {a.min_mapped_reads:g}", file=sys.stderr)
        sys.exit(DROP)
    write_slot(a.out, meta)


# -- multiqc --------------------------------------------------------------------


def simple_name(name: str) -> str:
    return Path(name).name.split(".", 1)[0]


def name_replacements(samples: str, reads: str) -> str:
    lines = []
    for sid, meta in metas(samples):
        first = (Path(reads) / sid / "reads.txt").read_text().split()
        paired = meta["single_end"] == "false"
        if simple_name(first[0]) != sid:
            lines.append(f"{simple_name(first[0])}\t{sid}{'_1' if paired else ''}")
            if paired:
                lines.append(f"{simple_name(first[1])}\t{sid}_2")
    return "".join(line + "\n" for line in lines)


def sample_merge_yaml(samplesheet: str) -> str:
    with open(samplesheet, newline="") as fh:
        ids = sorted({r["sample"].strip() for r in csv.DictReader(fh) if (r.get("fastq_2") or "").strip()})
    if not ids:
        return "table_sample_merge: {}\n"

    def pat(sid: str, read: int) -> str:
        esc = re.sub(r"[\\^$.|?*+()\[\]{}/]", lambda m: "\\" + m.group(0), sid).replace("'", "''")
        return f"    - type: regex\n      pattern: '(?<=^{esc})_{read}$'"

    r1 = "\n".join(pat(i, 1) for i in ids)
    r2 = "\n".join(pat(i, 2) for i in ids)
    return f'table_sample_merge:\n  "Read 1":\n{r1}\n  "Read 2":\n{r2}\n'


def inferexperiment_strandedness(path: Path, stranded_t: float, unstranded_t: float) -> dict:
    fwd = rev = unstr = 0.0
    pats = {
        "u": r"Fraction of reads failed to determine:\s([\d\.]+)",
        "f": r'Fraction of reads explained by "\++,--":\s([\d\.]+)',
        "r": r'Fraction of reads explained by "\+-,-\+":\s([\d\.]+)',
        "pf": r'Fraction of reads explained by "1\++,1--,2\+-,2-\+":\s([\d\.]+)',
        "pr": r'Fraction of reads explained by "1\+-,1-\+,2\+\+,2--":\s([\d\.]+)',
    }
    for line in path.read_text().splitlines():
        for k, p in pats.items():
            m = re.search(p, line)
            if m:
                v = f32(float(m.group(1))) * 100
                if k == "u":
                    unstr = v
                elif k in ("f", "pf"):
                    fwd = v
                else:
                    rev = v
    return calculate_strandedness(fwd, rev, unstr, stranded_t, unstranded_t)


def round1(v):
    return None if v is None else math.floor(v * 10 + 0.5) / 10.0


def certainty(an):
    if not an:
        return None
    stranded = an["forwardFragments"] + an["reverseFragments"]
    if stranded == 0:
        return None
    s = an["inferred_strandedness"]
    if s == "forward":
        return an["forwardFragments"] / stranded * 100
    if s == "reverse":
        return an["reverseFragments"] / stranded * 100
    return None


def strand_rows(a: argparse.Namespace) -> list[tuple]:
    """classifyStrand for every sample with an infer_experiment report."""
    strand = dict(metas(a.strand))
    rows = []
    for sid, _meta in metas(a.map_pass):
        ie = find_one(a.infer_experiment, f"{sid}.infer_experiment.txt")
        if ie is None:
            continue
        meta = strand[sid]
        rseqc = inferexperiment_strandedness(ie, a.stranded_threshold, a.unstranded_threshold)
        salmon = None
        if "salmon_inferred" in meta:
            salmon = {"inferred_strandedness": meta["salmon_inferred"], "forwardFragments": float(meta["salmon_fwd"]),
                      "reverseFragments": float(meta["salmon_rev"]),
                      "unstrandedFragments": float(meta["salmon_unstr"])}
            provided = "auto"
            ok = salmon["inferred_strandedness"] == rseqc["inferred_strandedness"] != "undetermined"
        else:
            provided = meta["strandedness"]
            ok = meta["strandedness"] == rseqc["inferred_strandedness"]
        rows.append((sid, provided, "pass" if ok else "fail", salmon, rseqc))
    return sorted(rows)


def load_asset(path: Path) -> dict:
    import yaml  # MultiQC image

    return {k: v for k, v in yaml.safe_load(path.read_text()).items() if not str(k).startswith("_")}


def strand_summary_json(static: dict, rows: list[tuple]) -> str:
    keys = list(static["headers"])
    data = {}
    for sid, provided, status, salmon, rseqc in rows:
        raw = {
            "provided": provided,
            "salmon_inferred": (salmon or {}).get("inferred_strandedness") or "-",
            "salmon_pct": round1(certainty(salmon)),
            "salmon_s": round1(salmon and salmon["forwardFragments"]),
            "salmon_a": round1(salmon and salmon["reverseFragments"]),
            "salmon_u": round1(salmon and salmon["unstrandedFragments"]),
            "rseqc_inferred": (rseqc or {}).get("inferred_strandedness") or "-",
            "rseqc_pct": round1(certainty(rseqc)),
            "rseqc_s": round1(rseqc and rseqc["forwardFragments"]),
            "rseqc_a": round1(rseqc and rseqc["reverseFragments"]),
            "rseqc_u": round1(rseqc and rseqc["unstrandedFragments"]),
            "status": status,
        }
        unknown = set(raw) - set(keys)
        if unknown:
            sys.exit(f"strand_check_summary.yaml headers do not declare columns: {sorted(unknown)}")
        data[sid] = {k: raw[k] for k in keys if raw.get(k) is not None}
    return json.dumps({**static, "data": data}, indent=4)


def strand_composition_json(static: dict, rows: list[tuple]) -> str:
    def comp(an):
        return {"Sense": round1(an["forwardFragments"]), "Antisense": round1(an["reverseFragments"]),
                "Unstranded": round1(an["unstrandedFragments"])}

    rseqc_data = {sid: comp(r) for sid, _p, _s, _sal, r in rows if r}
    salmon_data = {sid: comp(s) for sid, _p, _st, s, _r in rows if s}
    datasets, labels = [], []
    if rseqc_data:
        datasets.append(rseqc_data)
        labels.append("RSeQC")
    if salmon_data:
        datasets.append(salmon_data)
        labels.append("Salmon")
    config = dict(static)
    pconfig = dict(config["pconfig"])
    if len(datasets) > 1:
        pconfig["data_labels"] = [{"name": label, "ylab": pconfig.get("ylab")} for label in labels]
    config["pconfig"] = pconfig
    config["data"] = datasets[0] if len(datasets) == 1 else datasets
    return json.dumps(config, indent=4)


def cmd_multiqc(a: argparse.Namespace) -> None:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "name_replacement.txt").write_text(name_replacements(a.samples, a.reads))
    (out / "multiqc_sample_merge.yml").write_text(sample_merge_yaml(a.samplesheet))
    rows = strand_rows(a)
    if rows:  # an empty strand channel emits no section in the pipeline
        assets = Path(a.assets)
        summary = load_asset(assets / "strand_check_summary.yaml")
        composition = {**load_asset(assets / "strand_check_composition.yaml"),
                       **{k: summary[k] for k in ("parent_id", "parent_name", "parent_description")}}
        (out / "strand_check_summary_mqc.json").write_text(strand_summary_json(summary, rows))
        (out / "strand_check_composition_mqc.json").write_text(strand_composition_json(composition, rows))
    if a.trimgalore:  # chained port: the filter maps keep no fail rows, so rebuild them from the reports
        fails = trimmed_fails(metas(a.samples), a.trimgalore, a.min_trimmed_reads)
        if fails:
            (out / "fail_trimmed_samples_mqc.tsv").write_text(fail_trimmed_tsv(fails))
        fails = mapped_fails(metas(a.strand), a.star, a.min_mapped_reads)
        if fails:
            header = (Path(a.assets) / "sample_status_header.txt").read_text()
            (out / "fail_mapped_samples_mqc.tsv").write_text(
                fail_mapped_tsv(header, "STAR uniquely mapped reads", fails))
        return
    for status in (a.trim_status, a.map_status):
        for f in Path(status).glob("fail_*_mqc.tsv"):
            (out / f.name).write_text(f.read_text())


# -- selftest -------------------------------------------------------------------


def selftest() -> None:
    assert java_float_str(9000.0) == "9000.0" and java_float_str(4.52) == "4.52"
    assert java_float_str(12345678.0) == "1.2345678E7" and java_float_str(0.0) == "0.0"
    r = calculate_strandedness(10.4, 89.6, 0, 0.8, 0.1)
    assert r["inferred_strandedness"] == "reverse" and round1(certainty(r)) == 89.6
    assert calculate_strandedness(48, 52, 0, 0.8, 0.1)["inferred_strandedness"] == "unstranded"
    assert calculate_strandedness(30, 70, 0, 0.8, 0.1)["inferred_strandedness"] == "undetermined"
    assert round1(0.25) == 0.3 and round1(None) is None
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        sheet = t / "s.csv"
        sheet.write_text("sample,fastq_1,fastq_2,strandedness\nB.1,b1,b2,auto\nA,a1,,reverse\nB.1,b3,b4,auto\n")
        y = sample_merge_yaml(str(sheet))
        assert y == ("table_sample_merge:\n  \"Read 1\":\n    - type: regex\n      pattern: '(?<=^B\\.1)_1$'\n"
                     "  \"Read 2\":\n    - type: regex\n      pattern: '(?<=^B\\.1)_2$'\n"), y
        (t / "samples").mkdir()
        (t / "reads/A").mkdir(parents=True)
        (t / "reads/B.1").mkdir(parents=True)
        write_meta(t / "samples/A", {"single_end": "true", "strandedness": "reverse"})
        write_meta(t / "samples/B.1", {"single_end": "false", "strandedness": "auto"})
        (t / "reads/A/reads.txt").write_text("A.fastq.gz\n")
        (t / "reads/B.1/reads.txt").write_text("x_1.fq.gz\nx_2.fq.gz\nx3.fq.gz\nx4.fq.gz\n")
        assert name_replacements(str(t / "samples"), str(t / "reads")) == "x_1\tB.1_1\nx_2\tB.1_2\n"
        (t / "trim/0").mkdir(parents=True)
        (t / "trim/0/A_trimmed.fastq.gz_trimming_report.txt").write_text(
            "9500 sequences processed in total\nSequences removed because they became shorter than the length "
            "cutoff of 20 bp:\t100 (1.0%)\n")
        ns = argparse.Namespace(samples=str(t / "samples"), trimgalore=str(t / "trim"), min_trimmed_reads=10000,
                                passed=str(t / "p"), auto=str(t / "a"), status=str(t / "st"))
        cmd_trimmed(ns)
        assert sorted(p.name for p in (t / "p").iterdir()) == ["B.1"]  # no report: passes
        assert (t / "st/fail_trimmed_samples_mqc.tsv").read_text() == "Sample\tReads after trimming\nA\t9400.0\n"
        assert [p.name for p in (t / "a").iterdir()] == ["B.1"]

        def exit_code(fn, ns) -> int | str:
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    fn(ns)
            except SystemExit as e:
                return e.code
            return 0

        # chained port: one slot per sample, holding meta.env and that sample's reports
        for slot, sid in (("0", "A"), ("1", "B.1")):
            write_slot(str(t / "cat" / slot), {"id": sid, **read_meta(t / "samples" / sid)})
        (t / "trim/1").mkdir()
        (t / "cat/0/meta.env").rename(t / "trim/0/meta.env")
        (t / "cat/1/meta.env").rename(t / "trim/1/meta.env")
        assert [sid for sid, _ in metas(str(t / "trim"))] == ["A", "B.1"]
        assert metas(str(t / "trim"))[1][1] == {"id": "B.1", "single_end": "false", "strandedness": "auto"}
        ti = argparse.Namespace(slot=str(t / "trim/0"), min_trimmed_reads=10000.0, out=str(t / "ft/0"))
        assert exit_code(cmd_trim_item, ti) == DROP and not (t / "ft/0").exists()
        ti.min_trimmed_reads = 9400.0  # n == min passes (and is still a fail_trimmed row)
        assert exit_code(cmd_trim_item, ti) == 0 and slot_meta(str(t / "ft/0"))["id"] == "A"
        ti = argparse.Namespace(slot=str(t / "trim/1"), min_trimmed_reads=10000.0, out=str(t / "ft/1"))
        assert exit_code(cmd_trim_item, ti) == 0  # no report: passes
        assert slot_meta(str(t / "ft/1")) == slot_meta(str(t / "trim/1"))

        (t / "salmon/1").mkdir(parents=True)
        (t / "salmon/1/meta.env").write_text((t / "trim/1/meta.env").read_text())
        si = argparse.Namespace(slot=str(t / "salmon/1"), stranded_threshold=0.8, unstranded_threshold=0.1,
                                out=str(t / "strand/1"))
        assert exit_code(cmd_strand_item, si) not in (0, DROP)  # auto without lib_format_counts.json fails
        (t / "salmon/1/B.1_lib_format_counts.json").write_text(
            '{"num_assigned_fragments": 1000, "strand_mapping_bias": 0.1, "IU": 0, "U": 0, "MU": 0}')
        assert exit_code(cmd_strand_item, si) == 0
        m = slot_meta(str(t / "strand/1"))
        assert (m["id"], m["provided"], m["strandedness"], m["salmon_inferred"]) == ("B.1", "auto", "reverse", "reverse")
        (t / "salmon/0").mkdir()
        (t / "salmon/0/meta.env").write_text((t / "trim/0/meta.env").read_text())
        si.slot, si.out = str(t / "salmon/0"), str(t / "strand/0")
        assert exit_code(cmd_strand_item, si) == 0 and slot_meta(str(t / "strand/0"))["provided"] == "reverse"

        for slot, sid, pct in (("0", "A", "4.52"), ("1", "B.1", "91.30")):
            (t / "star" / slot).mkdir(parents=True)
            (t / "star" / slot / f"{sid}.Log.final.out").write_text(f"   Uniquely mapped reads % |\t{pct}%\n")
            (t / "sorti" / slot).mkdir(parents=True)
            (t / "sorti" / slot / "meta.env").write_text((t / "trim" / slot / "meta.env").read_text())
        mi = argparse.Namespace(slot=str(t / "sorti/0"), star=str(t / "star/0"), meta=str(t / "strand/0/meta.env"),
                                min_mapped_reads=5.0, out=str(t / "fm/0"))
        assert exit_code(cmd_map_item, mi) == DROP and not (t / "fm/0").exists()
        mi.min_mapped_reads = 4.52  # pm == min passes
        assert exit_code(cmd_map_item, mi) == 0 and slot_meta(str(t / "fm/0")) == slot_meta(str(t / "strand/0"))
        mi.meta = str(t / "strand/1/meta.env")  # zip paired the wrong sample
        assert exit_code(cmd_map_item, mi) not in (0, DROP)
        mi = argparse.Namespace(slot=str(t / "sorti/1"), star=str(t / "star/1"), meta=str(t / "strand/1/meta.env"),
                                min_mapped_reads=5.0, out=str(t / "fm/1"))
        assert exit_code(cmd_map_item, mi) == 0 and slot_meta(str(t / "fm/1"))["strandedness"] == "reverse"

        # fail tables: the chained rebuild matches the faithful port's filter tasks byte for byte
        (t / "assets").mkdir()
        (t / "assets/sample_status_header.txt").write_text("# id: 'fail_mapped_samples'\n")
        cmd_strandedness(argparse.Namespace(samples=str(t / "samples"), salmon=str(t / "salmon"),
                                            stranded_threshold=0.8, unstranded_threshold=0.1, out=str(t / "sp")))
        cmd_mapped(argparse.Namespace(samples=str(t / "sp"), star=str(t / "star"), min_mapped_reads=5.0,
                                      status_header=str(t / "assets/sample_status_header.txt"),
                                      aligner_display_name="STAR uniquely mapped reads",
                                      passed=str(t / "mp"), stranded=str(t / "msp"), status=str(t / "mst")))
        assert sorted(p.name for p in (t / "mp").iterdir()) == ["B.1"]
        common = dict(samplesheet=str(sheet), samples=str(t / "samples"), reads=str(t / "reads"),
                      map_pass=str(t / "fm"), infer_experiment=str(t / "none"), assets=str(t / "assets"),
                      stranded_threshold=0.8, unstranded_threshold=0.1)
        cmd_multiqc(argparse.Namespace(**common, strand=str(t / "sp"), out=str(t / "q_old"),
                                       trim_status=str(t / "st"), map_status=str(t / "mst"), trimgalore=None))
        cmd_multiqc(argparse.Namespace(**common, strand=str(t / "strand"), out=str(t / "q_new"), trim_status=None,
                                       map_status=None, trimgalore=str(t / "trim"), star=str(t / "star"),
                                       min_trimmed_reads=10000.0, min_mapped_reads=5.0))
        for name in ("fail_trimmed_samples_mqc.tsv", "fail_mapped_samples_mqc.tsv"):
            assert (t / "q_old" / name).read_bytes() == (t / "q_new" / name).read_bytes(), name
        assert (t / "q_new/fail_mapped_samples_mqc.tsv").read_text() == (
            "# id: 'fail_mapped_samples'\nSample\tSTAR uniquely mapped reads (%)\nA\t4.52\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    t = sub.add_parser("trimmed")
    t.add_argument("--samples", required=True)
    t.add_argument("--trimgalore", required=True)
    t.add_argument("--min-trimmed-reads", type=float, required=True)
    t.add_argument("--pass", dest="passed", required=True)
    t.add_argument("--auto", required=True)
    t.add_argument("--status", required=True)

    s = sub.add_parser("strandedness")
    s.add_argument("--samples", required=True)
    s.add_argument("--salmon", required=True)
    s.add_argument("--stranded-threshold", type=float, required=True)
    s.add_argument("--unstranded-threshold", type=float, required=True)
    s.add_argument("--out", required=True)

    m = sub.add_parser("mapped")
    m.add_argument("--samples", required=True)
    m.add_argument("--star", required=True)
    m.add_argument("--min-mapped-reads", type=float, required=True)
    m.add_argument("--status-header", required=True)
    m.add_argument("--aligner-display-name", default="STAR uniquely mapped reads")
    m.add_argument("--pass", dest="passed", required=True)
    m.add_argument("--stranded", required=True)
    m.add_argument("--status", required=True)

    q = sub.add_parser("multiqc")
    for opt in ("samplesheet", "samples", "reads", "strand", "map-pass", "infer-experiment", "assets", "out"):
        q.add_argument(f"--{opt}", required=True)
    q.add_argument("--stranded-threshold", type=float, required=True)
    q.add_argument("--unstranded-threshold", type=float, required=True)
    # fail tables: copied from the filter tasks' status folders, or rebuilt from the reports (chained port)
    q.add_argument("--trim-status")
    q.add_argument("--map-status")
    q.add_argument("--trimgalore")
    q.add_argument("--star")
    q.add_argument("--min-trimmed-reads", type=float)
    q.add_argument("--min-mapped-reads", type=float)

    ti = sub.add_parser("trim-item")
    ti.add_argument("--slot", required=True)
    ti.add_argument("--min-trimmed-reads", type=float, required=True)
    ti.add_argument("--out", required=True)

    si = sub.add_parser("strand-item")
    si.add_argument("--slot", required=True)
    si.add_argument("--stranded-threshold", type=float, required=True)
    si.add_argument("--unstranded-threshold", type=float, required=True)
    si.add_argument("--out", required=True)

    mi = sub.add_parser("map-item")
    mi.add_argument("--slot", required=True)
    mi.add_argument("--star", required=True)
    mi.add_argument("--meta", required=True)
    mi.add_argument("--min-mapped-reads", type=float, required=True)
    mi.add_argument("--out", required=True)

    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    if not a.cmd:
        ap.error("pick a subcommand or --selftest")
    if a.cmd == "multiqc" and not (
            (a.trim_status and a.map_status)
            or (a.trimgalore and a.star and a.min_trimmed_reads is not None and a.min_mapped_reads is not None)):
        ap.error("multiqc needs --trim-status and --map-status, or --trimgalore, --star and both minimums")
    {"trimmed": cmd_trimmed, "strandedness": cmd_strandedness, "mapped": cmd_mapped, "multiqc": cmd_multiqc,
     "trim-item": cmd_trim_item, "strand-item": cmd_strand_item, "map-item": cmd_map_item}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
