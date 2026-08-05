"""Fail if a workflow.yaml still has un-promoted root inputs (not sanitized).

Mirrors `horus sanitize` idempotency: a sanitized workflow has no root inputs
left, so `find_root_inputs` returns []. A workflow with no top-level `edges:`
block can't be sanitized at all (fan-out/map) and is skipped, not failed.
"""

import sys
from pathlib import Path

from horus_runtime.cli import HorusContext
from horus_runtime.core.workflow.base import BaseWorkflow
from horus_runtime.sanitize import SanitizeError, apply_promotions, find_root_inputs


def status(path: Path) -> str:
    wf = BaseWorkflow.from_yaml(path)
    roots, _missing = find_root_inputs(wf)
    if not roots:
        return "clean"
    text = path.read_text(encoding="utf-8")
    try:
        out = apply_promotions(text, roots)
    except SanitizeError:
        return "skip"  # no edges block to extend; nothing to enforce
    return "dirty" if out != text else "clean"


def main(argv: list[str]) -> int:
    ctx = HorusContext.boot()
    dirty: list[Path] = []
    try:
        for arg in argv:
            p = Path(arg)
            s = status(p)
            print(f"{s:5} {p}")
            if s == "dirty":
                dirty.append(p)
    finally:
        ctx.shutdown()
    if dirty:
        print("\nNot sanitized. Run: horus sanitize <file> -o <file> -y")
        for p in dirty:
            print(f"  {p}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
