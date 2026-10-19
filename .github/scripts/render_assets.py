"""Render every workflows/**/assets/*.svg to a PNG next to it.

Run from the repo root: uv run --with cairosvg python .github/scripts/render_assets.py [paths...]
With no paths, renders all assets in the repo.
"""

import sys
from pathlib import Path

import cairosvg

svgs = [Path(p) for p in sys.argv[1:]] or sorted(Path("workflows").glob("**/assets/*.svg"))
for svg in svgs:
    cairosvg.svg2png(url=str(svg), write_to=str(svg.with_suffix(".png")))
    print(svg.with_suffix(".png"))
