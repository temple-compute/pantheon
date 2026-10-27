# W-46 · Bank Transaction Categoriser - Fine-tune & Compare Runs

Fine-tune a small pretrained encoder to sort card transactions into spending categories, one comparable report per run.

![Domain: AI](https://img.shields.io/badge/domain-ai-blue) ![horus-runtime](https://img.shields.io/badge/horus--runtime-workflow-green)

## Overview

Fine-tunes a pretrained text encoder (default [distilbert-base-multilingual-cased](https://huggingface.co/distilbert/distilbert-base-multilingual-cased)) with Hugging Face Transformers to classify transaction descriptions such as `PUBLIX 7860 UNIVERSITY LN OAKLAND CA` into categories. Each run ends in an HTML report with its metrics, confusion matrix, training time, hardware and hyperparameters, so runs launched with different settings can be compared side by side. The workflow has 4 tasks.

## Pipeline

```
prepare_data  ──► train / val / test splits + label map      (small_cpu, cached)
   └─► train  ──► fine-tuned checkpoint + training log       (trainer: CPU or L4 GPU)
         └─► evaluate  ──► metrics.json + confusion_matrix.png   (small_cpu)
               └─► report  ──► report.html                       (small_cpu)
```

`prepare_data` only sees the data inputs and splits with a fixed seed, so runs that change only hyperparameters reuse its output. `train` runs on its own `trainer` target. Point it at an L4 machine and set `gpus: 1` to train on GPU; the script uses CUDA whenever a GPU is present and records the hardware in the report.

## Inputs / Outputs

- Input: a CSV with one transaction per row, a description column and a category column. The example `examples/transactions.csv` is a stratified 5,000-row sample (17 categories) of the synthetic, MIT-licensed [DoDataThings/us-bank-transaction-categories-v2](https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2). Swap in your own or anonymised data and set the column names.
- `data/{train,val,test}.csv`, `data/label_map.json`: the cleaned stratified 80/10/10 split.
- `model/`: fine-tuned checkpoint and tokenizer.
- `logs/train_log.jsonl`, `logs/train_summary.json`: training log, wall time, hardware and hyperparameters.
- `results/metrics.json`, `results/confusion_matrix.png`: test accuracy, macro F1, per-class precision/recall/F1, confusion matrix.
- `results/report.html`: the run report.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `transactions_csv` | `examples/transactions.csv` | Transactions CSV |
| `text_column` | `description` | Column with the transaction description |
| `label_column` | `category` | Column with the spending category |
| `model_name` | `distilbert-base-multilingual-cased` | Hugging Face model to fine-tune |
| `learning_rate` | 1e-4 | Peak learning rate |
| `epochs` | 3 | Passes over the training split |
| `batch_size` | 32 | Examples per optimizer step |
| `max_length` | 32 | Max tokens per description |
| `seed` | 42 | Training seed (the split always uses 42) |

## References

- [Hugging Face Transformers](https://github.com/huggingface/transformers): `Trainer` and the pretrained model.
- [DoDataThings/us-bank-transaction-categories-v2](https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2): synthetic US bank transaction descriptions, 17 categories.
- Sanh et al., "DistilBERT, a distilled version of BERT", [arXiv:1910.01108](https://arxiv.org/abs/1910.01108).
