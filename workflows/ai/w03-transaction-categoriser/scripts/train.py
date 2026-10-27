"""
Fine-tune a pretrained encoder (default distilbert-base-multilingual-cased) to
classify transaction descriptions, evaluating on the validation split each
epoch. Uses CUDA when the target has a GPU, CPU otherwise, and records which
hardware ran in the summary so campaign runs can be compared.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time

import numpy as np
import pandas as pd
import torch
import transformers
from datasets import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
    set_seed,
)


def hardware() -> dict:
    if torch.cuda.is_available():
        return {"device": "cuda", "name": torch.cuda.get_device_name(0), "gpus": torch.cuda.device_count()}
    name = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as f:
            name = next(l.split(":", 1)[1].strip() for l in f if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    return {"device": "cpu", "name": name, "cpus": os.cpu_count(), "torch_threads": torch.get_num_threads()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--train", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--label_map", required=True)
    p.add_argument("--model_name", required=True)
    p.add_argument("--learning_rate", type=float, required=True)
    p.add_argument("--epochs", type=float, required=True)
    p.add_argument("--batch_size", type=lambda v: int(float(v)), required=True)
    p.add_argument("--max_length", type=lambda v: int(float(v)), required=True)
    p.add_argument("--seed", type=lambda v: int(float(v)), required=True)
    p.add_argument("--out_model", required=True)
    p.add_argument("--out_log", required=True)
    p.add_argument("--out_summary", required=True)
    args = p.parse_args()

    set_seed(args.seed)
    labels = json.load(open(args.label_map))["labels"]
    label2id = {l: i for i, l in enumerate(labels)}

    tok = AutoTokenizer.from_pretrained(args.model_name)

    def load(path: str) -> Dataset:
        df = pd.read_csv(path, dtype=str)
        ds = Dataset.from_dict({"text": df["text"].tolist(), "label": [label2id[l] for l in df["label"]]})
        return ds.map(lambda b: tok(b["text"], truncation=True, max_length=args.max_length), batched=True)

    train_ds, val_ds = load(args.train), load(args.val)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=len(labels),
        id2label=dict(enumerate(labels)),
        label2id=label2id,
    )

    def accuracy(pred) -> dict:
        return {"accuracy": float((np.argmax(pred.predictions, axis=-1) == pred.label_ids).mean())}

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir="trainer_tmp",
            learning_rate=args.learning_rate,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            per_device_eval_batch_size=args.batch_size * 2,
            warmup_steps=0.1,  # <1 is a fraction of total steps (transformers 5)
            weight_decay=0.01,
            eval_strategy="epoch",
            save_strategy="no",
            logging_steps=10,
            report_to="none",
            seed=args.seed,
        ),
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tok,
        data_collator=DataCollatorWithPadding(tok),
        compute_metrics=accuracy,
    )

    t0 = time.time()
    trainer.train()
    train_seconds = time.time() - t0

    trainer.save_model(args.out_model)
    tok.save_pretrained(args.out_model)
    os.makedirs(os.path.dirname(args.out_log) or ".", exist_ok=True)
    with open(args.out_log, "w") as f:
        for row in trainer.state.log_history:
            f.write(json.dumps(row) + "\n")

    summary = {
        "train_seconds": round(train_seconds, 1),
        "hardware": hardware(),
        "hyperparameters": {
            "model_name": args.model_name,
            "learning_rate": args.learning_rate,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "max_length": args.max_length,
            "seed": args.seed,
        },
        "train_rows": len(train_ds),
        "val_rows": len(val_ds),
        "num_labels": len(labels),
        "steps": trainer.state.global_step,
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__, "python": platform.python_version()},
    }
    with open(args.out_summary, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
