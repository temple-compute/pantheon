"""Group influenza segment FASTA records by sample.

Conceptually the OrganizeBySample stage of a typical influenza genotyping
pipeline (e.g. FluTyper): headers look like ``>Sample01_HA_2024_Spain`` or
``>Sample01|NA|Hebei_SJ27``; first token = sample ID, second = segment.
Malformed headers (or duplicated sample/segment pairs) never abort the run;
they are appended to ``errors.log``, mirroring ``pipeline_errors.log``.

Usage:
    organize_by_sample.py --fasta in.fasta --segments segments.csv \
        --samples-dir samples/ --errors errors.log
    organize_by_sample.py --selftest

Outputs: segments.csv (sample,segment,length,header), one <sample>.fasta per
sample (headers normalised to ``sample|segment``), errors.log.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from pathlib import Path

SEGMENTS = {"PB2", "PB1", "PA", "HA", "NP", "NA", "MP", "M", "NS"}


def read_fasta(path: Path):
    header, seq = None, []
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            if header is not None:
                yield header, "".join(seq)
            header, seq = line[1:].strip(), []
        elif line.strip():
            seq.append(line.strip())
    if header is not None:
        yield header, "".join(seq)


def parse_header(header: str):
    """Return (sample, segment) or raise ValueError."""
    parts = re.split(r"[|_]", header.split()[0] if header.split() else "")
    if len(parts) < 2 or not parts[0]:
        raise ValueError("expected '<sample>_<segment>_...' or '<sample>|<segment>|...'")
    segment = parts[1].upper()
    if segment not in SEGMENTS:
        raise ValueError(f"unknown segment '{parts[1]}'")
    return parts[0], "MP" if segment == "M" else segment


def organize(records):
    rows, by_sample, errors, seen = [], {}, [], set()
    for header, seq in records:
        try:
            sample, segment = parse_header(header)
        except ValueError as exc:
            errors.append(f"malformed header '{header}': {exc}")
            continue
        if (sample, segment) in seen:
            errors.append(f"duplicate segment {sample}/{segment}: '{header}' ignored")
            continue
        seen.add((sample, segment))
        rows.append((sample, segment, len(seq), header))
        by_sample.setdefault(sample, {})[segment] = seq
    return sorted(rows), by_sample, errors


def write_outputs(rows, by_sample, errors, segments_csv, samples_dir, errors_log):
    with open(segments_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample", "segment", "length", "header"])
        w.writerows(rows)
    samples_dir.mkdir(parents=True, exist_ok=True)
    for sample, segs in sorted(by_sample.items()):
        with open(samples_dir / f"{sample}.fasta", "w") as fh:
            for seg, seq in sorted(segs.items()):
                fh.write(f">{sample}|{seg}\n{seq}\n")
    Path(errors_log).write_text("".join(f"{e}\n" for e in errors))


def selftest():
    recs = [("S1_HA_2024_ES", "ATG"), ("S1|NA|x", "ATGA"), ("S2", "AT"),
            ("S1_HA_dup", "A"), ("S3_XX_1", "A"), ("S3_M_1", "AC")]
    rows, by_sample, errors = organize(recs)
    assert [r[:3] for r in rows] == [("S1", "HA", 3), ("S1", "NA", 4), ("S3", "MP", 2)], rows
    assert len(errors) == 3, errors
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        write_outputs(rows, by_sample, errors, d / "s.csv", d / "samples", d / "e.log")
        assert (d / "samples" / "S1.fasta").read_text() == ">S1|HA\nATG\n>S1|NA\nATGA\n"
    print("organize_by_sample selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fasta", type=Path)
    ap.add_argument("--segments", type=Path)
    ap.add_argument("--samples-dir", type=Path)
    ap.add_argument("--errors", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.fasta and a.segments and a.samples_dir and a.errors):
        ap.error("--fasta, --segments, --samples-dir and --errors are required")
    for p in (a.segments, a.errors):
        p.parent.mkdir(parents=True, exist_ok=True)
    rows, by_sample, errors = organize(read_fasta(a.fasta))
    write_outputs(rows, by_sample, errors, a.segments, a.samples_dir, a.errors)
    print(f"{len(rows)} segments, {len(by_sample)} samples, {len(errors)} errors")


if __name__ == "__main__":
    sys.exit(main())
