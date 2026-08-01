#!/usr/bin/env python3
"""Small, measurable workload: hold a few hundred MB, burn CPU for a few seconds.

Deliberately stdlib-only so the exact same file runs unchanged under the
system interpreter (`shell` executor) and inside a provisioned virtualenv
(`uv_python_environment` executor). It records `sys.executable` so a reader
can tell, from the output alone, *which* interpreter actually ran it.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time


def burn(mb: int, seconds: float) -> tuple[int, int]:
    """Touch `mb` MiB of pages and spin the CPU for `seconds`.

    Every page is written to, not just allocated: an untouched bytearray is
    virtual-only on Linux and would never show up in RSS.
    """
    buf = bytearray(mb << 20)
    for i in range(0, len(buf), 4096):
        buf[i] = 1
    end = time.monotonic() + seconds
    iterations = 0
    while time.monotonic() < end:
        pow(3, 100_000, 99991)
        iterations += 1
    return len(buf), iterations


def peak_rss_mb() -> float:
    """Peak RSS of this process, in MiB (ru_maxrss is bytes on macOS, KiB elsewhere)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024**2 if sys.platform == "darwin" else peak / 1024


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True, help="execution path this run exercises")
    ap.add_argument("--out", required=True, help="where to write the stamp JSON")
    ap.add_argument("--prev", default=None, help="upstream stamp JSON, if any")
    ap.add_argument("--mb", type=int, default=300)
    ap.add_argument("--seconds", type=float, default=4.0)
    args = ap.parse_args()

    started = time.time()
    nbytes, iterations = burn(args.mb, args.seconds)
    elapsed = time.time() - started

    chain = []
    if args.prev:
        with open(args.prev, encoding="utf-8") as fh:
            chain = json.load(fh).get("chain", [])

    stamp = {
        "label": args.label,
        "python": sys.executable,
        "pid": os.getpid(),
        "allocated_mb": nbytes >> 20,
        "cpu_iterations": iterations,
        "elapsed_s": round(elapsed, 2),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "chain": [*chain, args.label],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(stamp, fh, indent=2)
    print(json.dumps(stamp))


if __name__ == "__main__":
    main()
