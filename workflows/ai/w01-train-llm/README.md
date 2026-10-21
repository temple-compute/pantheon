# W-28 · LLM From Scratch - Pretrain, SFT & Eval

Pretrain a decoder-only Transformer from scratch on the Pile, instruction-tune it on Alpaca/Dolly/GSM8K and score GSM8K accuracy.

![Status: WIP](https://img.shields.io/badge/WIP-red) ![Domain: AI](https://img.shields.io/badge/domain-ai-blue)

> [!WARNING]
> **This workflow is not yet complete.**
>
> The workflow is currently under development and should be considered a work in progress. Some stages may be incomplete, experimental, or subject to change. Use it for reference or testing only until it is finalized.

## Overview

Trains a small decoder-only Transformer from scratch with [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) (pinned to commit `bdd480a`): tokenize Pile text and instruction data, pretrain, supervised fine-tune (SFT) on Alpaca/Dolly/GSM8K, then score GSM8K accuracy. Preference pairs and RL prompts are also prepared for a future DPO/PPO workflow. The workflow has 9 tasks.

## Pipeline

```
clone_repo
   ├─► prepare_pretrain_val / prepare_pretrain_train  ──► pile_dev.h5 / pile_train.h5
   │        └─► train_pretrain  ──► base_pretrained.pt
   │                 └─► train_sft  ──► sft.pt
   │                          └─► eval_sft  ──► stage_table.jsonl
   ├─► prepare_sft_data         ──► sft_packed.h5 (feeds train_sft)
   ├─► prepare_preference_data  ──► preferences.jsonl (unused here)
   └─► prepare_rl_prompts       ──► rl_prompts_*.jsonl (unused here)
```

## Inputs / Outputs

- Inputs: none. The repo and datasets (Pile shards, Alpaca, Dolly, GSM8K, HH-RLHF, UltraFeedback) are fetched at runtime.
- `ckpts/base_pretrained.pt`, `ckpts/sft.pt`: pretrained and SFT checkpoints.
- `logs/pretrain.jsonl`, `logs/sft.jsonl`: pretraining and SFT metrics logs.
- `logs/stage_table.jsonl`: GSM8K accuracy of the SFT checkpoint.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `config_scale` | `configs/smoke` | `configs/smoke` (2 blocks, 20 steps) or `configs` (24 blocks, 50k steps) |
| `pretrain_steps` | 0 | Pretraining steps; 0 keeps the config value. Override also sets warmup to steps/20 + 1 |
| `sft_steps` | 0 | SFT steps; 0 keeps the config epochs. Override also sets warmup to steps/20 + 1 |
| `num_shards` | 1 | Pile training shards to stream and tokenize (1-30) |
| `pretrain_max_tokens` | 2000000000 | Stop tokenizing after this many tokens; 0 keeps all |
| `max_per_source` | 40000 | Preference pairs per source (HH-RLHF, UltraFeedback) |

## References

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) — source repo cloned by this workflow.
- [horus-runtime](https://github.com/temple-compute/horus-runtime) — workflow engine and plugin framework.
- [horus-environments](https://github.com/temple-compute/horus-environments) — horus plugin for conda-based Python environments.
