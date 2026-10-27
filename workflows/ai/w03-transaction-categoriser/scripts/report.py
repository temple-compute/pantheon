#!/usr/bin/env python3
"""
One self-contained HTML page per training run: headline metrics, hardware and
training time, the run's hyperparameters, per-epoch validation accuracy,
per-class scores and the confusion matrix. The hyperparameters are in the
<title> so reports from a campaign are easy to tell apart side by side.

stdlib only.
"""

import argparse
import base64
import html
import json
from pathlib import Path


def build(metrics: Path, summary: Path, log: Path, png: Path, out: Path) -> None:
    m = json.loads(metrics.read_text())
    s = json.loads(summary.read_text())
    hp = s["hyperparameters"]
    hw = s["hardware"]
    epochs = [r for r in map(json.loads, log.read_text().splitlines()) if "eval_accuracy" in r]
    esc = lambda v: html.escape(str(v))  # noqa: E731

    hw_text = f"{hw['name']} ({hw['device'].upper()}" + (
        f", {hw['gpus']} GPU)" if hw["device"] == "cuda" else f", {hw['cpus']} cores)"
    )
    hp_rows = "".join(f"<tr><th>{esc(k.replace('_', ' '))}</th><td>{esc(v)}</td></tr>" for k, v in hp.items())
    epoch_rows = "".join(
        f"<tr><td>{r['epoch']:.2g}</td><td>{r['eval_loss']:.4f}</td><td>{r['eval_accuracy']:.4f}</td></tr>"
        for r in epochs
    )
    worst_first = sorted(m["per_class"].items(), key=lambda kv: kv[1]["f1"])
    class_rows = "".join(
        f"<tr><td>{esc(l)}</td><td>{c['precision']:.3f}</td><td>{c['recall']:.3f}</td>"
        f"<td>{c['f1']:.3f}</td><td>{c['support']}</td></tr>"
        for l, c in worst_first
    )
    img = base64.b64encode(png.read_bytes()).decode()
    tag = f"lr {hp['learning_rate']:g} · {hp['epochs']:g} ep · bs {hp['batch_size']} · len {hp['max_length']} · seed {hp['seed']}"

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transaction classifier · {esc(tag)}</title>
<style>
:root {{ --bg:#faf9f6; --fg:#0f1419; --accent:#b07d48; --muted:#5a6578; --grid:#c9c4b8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1419; --fg:#faf9f6; --accent:#d4a574; --muted:#8fa3bf; --grid:#3a4556; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; max-width:820px; margin:2rem auto; padding:0 16px; }}
table {{ border-collapse:collapse; width:100%; margin:.5rem 0 1.5rem; }} th,td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--grid); }}
th {{ font-weight:500; }} .kpis {{ display:flex; flex-wrap:wrap; gap:1rem 2rem; margin:1rem 0 1.5rem; }}
.kpi b {{ display:block; font-size:1.6rem; color:var(--accent); }} .kpi span {{ color:var(--muted); font-size:.85rem; }}
img {{ max-width:100%; height:auto; background:#fff; border-radius:4px; }} .tag {{ color:var(--muted); }}
</style></head><body>
<h1>Transaction categorisation run</h1>
<p class="tag">{esc(hp['model_name'])} · {esc(tag)}</p>
<div class="kpis">
<div class="kpi"><b>{m['accuracy']:.1%}</b><span>test accuracy</span></div>
<div class="kpi"><b>{m['macro_f1']:.3f}</b><span>macro F1</span></div>
<div class="kpi"><b>{s['train_seconds'] / 60:.1f} min</b><span>training time</span></div>
<div class="kpi"><b>{len(m['labels'])}</b><span>classes</span></div>
</div>
<p>Trained on {esc(hw_text)}, {s['train_rows']} training rows, {s['steps']} steps; tested on {m['test_rows']} held-out rows.
torch {esc(s['versions']['torch'])}, transformers {esc(s['versions']['transformers'])}.</p>
<h2>Hyperparameters</h2>
<table>{hp_rows}</table>
<h2>Validation per epoch</h2>
<table><tr><th>Epoch</th><th>Loss</th><th>Accuracy</th></tr>{epoch_rows}</table>
<h2>Per-class scores (test, weakest first)</h2>
<table><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr>{class_rows}</table>
<h2>Confusion matrix</h2>
<img src="data:image/png;base64,{img}" alt="Confusion matrix of true versus predicted categories on the test split">
</body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)


def main():
    p = argparse.ArgumentParser(description="Build the run report.")
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--png", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build(a.metrics, a.summary, a.log, a.png, a.out)
    print(f"report -> {a.out}")


if __name__ == "__main__":
    main()
