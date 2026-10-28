"""
Score the fine-tuned model on the held-out test split: accuracy, macro F1,
per-class precision/recall/F1 and a confusion matrix (JSON + PNG).
"""

from __future__ import annotations

import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from transformers import AutoModelForSequenceClassification, AutoTokenizer


@torch.no_grad()
def predict(model_dir: str, texts: list[str], max_length: int, batch_size: int = 128) -> list[str]:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device).eval()
    preds = []
    for i in range(0, len(texts), batch_size):
        enc = tok(texts[i : i + batch_size], truncation=True, max_length=max_length, padding=True, return_tensors="pt")
        logits = model(**enc.to(device)).logits
        preds += [model.config.id2label[j] for j in logits.argmax(-1).tolist()]
    return preds


def plot(cm, labels: list[str], out: str) -> None:
    norm = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    size = max(6, 0.45 * len(labels) + 2)
    fig, ax = plt.subplots(figsize=(size, size))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=7,
                        color="white" if norm[i, j] > 0.5 else "black")
    ax.set_title("Confusion matrix (test split, counts; colour = row-normalised)")
    fig.tight_layout()
    fig.savefig(out, dpi=120)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--label_map", required=True)
    p.add_argument("--max_length", type=lambda v: int(float(v)), required=True)
    p.add_argument("--out_metrics", required=True)
    p.add_argument("--out_png", required=True)
    args = p.parse_args()

    labels = json.load(open(args.label_map))["labels"]
    df = pd.read_csv(args.test, dtype=str)
    y_true = df["label"].tolist()
    y_pred = predict(args.model, df["text"].tolist(), args.max_length)

    prec, rec, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0),
        "test_rows": len(df),
        "per_class": {
            l: {"precision": float(prec[i]), "recall": float(rec[i]), "f1": float(f1[i]), "support": int(support[i])}
            for i, l in enumerate(labels)
        },
        "labels": labels,
        "confusion_matrix": cm.tolist(),
    }

    os.makedirs(os.path.dirname(args.out_metrics) or ".", exist_ok=True)
    with open(args.out_metrics, "w") as f:
        json.dump(metrics, f, indent=2)
    plot(cm, labels, args.out_png)
    print(f"accuracy {metrics['accuracy']:.4f}  macro F1 {metrics['macro_f1']:.4f}  on {len(df)} test rows")


if __name__ == "__main__":
    main()
