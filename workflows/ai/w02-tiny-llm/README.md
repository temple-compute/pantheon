# W-29 · Tiny LLM From Scratch - TinyStories Pretrain & Sample

Pretrain a tiny decoder-only Transformer from scratch on TinyStories and sample a story from it.

![Domain: AI](https://img.shields.io/badge/domain-ai-blue) ![horus-runtime](https://img.shields.io/badge/horus--runtime-workflow-green)

<img width="1080" height="929" alt="train-llm-cropped" src="https://github.com/user-attachments/assets/6b4a80ef-bf49-473d-9e85-c76f69373673" />

## Overview

A small-data companion to [W-28](../w01-train-llm/README.md): pretrains the same from-scratch decoder-only Transformer ([train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch), commit `bdd480a`) on [TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories) and samples a story from the checkpoint. The workflow has 5 tasks.

## Pipeline

```
clone_repo
   ├─► prepare_tinystories_train / prepare_tinystories_val  ──► tinystories_{train,val}.h5
   │        └─► train_pretrain_tiny  ──► tinystories_pretrained.pt
   │                 └─► sample_story  ──► tinystories_sample.txt
```

## Inputs / Outputs

- Inputs: none. The repo and TinyStories are fetched at runtime.
- `ckpts/tinystories_pretrained.pt`: pretrained checkpoint.
- `logs/pretrain.jsonl`: pretraining metrics log.
- `samples/tinystories_sample.txt`: greedy, raw (no chat template) continuation of the prompt.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `config_scale` | `configs/smoke` | `configs/smoke` (2 blocks, 20 steps) or `configs` (24 blocks, 50k steps) |
| `pretrain_steps` | 0 | Pretraining steps; 0 keeps the config value. Override also sets warmup to steps/20 + 1 |
| `train_docs` | 20000 | TinyStories training stories to tokenize (full split ~2.1M) |
| `val_docs` | 2000 | Validation stories to tokenize |
| `prompt` | `Once upon a time,` | Opening the model continues |
| `max_new_tokens` | 200 | Sample length |

## References

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) — source repo cloned by this workflow.
- [TinyStories dataset](https://huggingface.co/datasets/roneneldan/TinyStories) · [paper](https://arxiv.org/abs/2305.07759) — short, simple GPT-generated children's stories.
- [horus-runtime](https://github.com/temple-compute/horus-runtime) — workflow engine and plugin framework.
- [horus-environments](https://github.com/temple-compute/horus-environments) — horus plugin for conda-based Python environments.
