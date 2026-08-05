# W-28 · LLM From Scratch - Pretrain, SFT & Eval

![Domain: AI](https://img.shields.io/badge/WIP-red) ![Domain: AI](https://img.shields.io/badge/domain-ai-blue)

> [!WARNING]
> **This workflow is not yet complete.**
>
> The workflow is currently under development and should be considered a work in progress. Some stages may be incomplete, experimental, or subject to change. Use it for reference or testing only until it is finalized.


## Overview

Trains a small decoder-only Transformer from scratch, end to end: clone
[train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) → tokenize
Pile text and instruction data → pretrain the base model → supervised fine-tune (SFT) it on
Alpaca/Dolly/GSM8K → evaluate GSM8K accuracy. It exists as a Horus workflow so each stage
(data prep, pretraining, fine-tuning, eval) is a resumable, individually-rerunnable task with
explicit inputs/outputs instead of one long shell script.

## Pipeline

```
clone_repo (local)
   │
   ├─► prepare_pretrain_val / prepare_pretrain_train  ──► pile_dev.h5 / pile_train.h5
   │        └─► train_pretrain (local)                ──► base_pretrained.pt
   │                 └─► train_sft (local)             ──► sft.pt
   │                          └─► eval_sft (local)      ──► stage_table.jsonl (GSM8K acc)
   │
   ├─► prepare_sft_data           ──► sft_packed.h5 (feeds train_sft)
   ├─► prepare_preference_data    ──► preferences.jsonl (unused here; for a future reward/DPO workflow)
   └─► prepare_rl_prompts         ──► rl_prompts_*.jsonl (unused here; for a future PPO/GRPO workflow)
```

Reward-model, DPO, PPO, and GRPO stages are out of scope for this workflow. The data they need
is already produced by `prepare_preference_data`/`prepare_rl_prompts`; a follow-up workflow can
pick those up.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the horus-runtime and plugins (one time)
uv sync
# or: pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

Outputs land under `workflow_results/`: `repo/` (the cloned training repo), `data/` (tokenized
datasets), `ckpts/base_pretrained.pt` + `ckpts/sft.pt` (checkpoints), and `logs/stage_table.jsonl`
(GSM8K accuracy for the SFT checkpoint).

## Tools & Dependencies

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) (cloned at
  runtime by `clone_repo`) — pure PyTorch, no `transformers`/`trl`/`peft`.
- `torch`, `numpy`, `h5py`, `datasets`, `tiktoken`, `wandb` — provisioned via `conda_env.yaml`
  (micromamba) by the `conda_python_environment` executor.
- `git` — used by the `shell` executor to clone the repo.

## Horus Configuration

Every task runs `target: {kind: local}`, either on the bare `shell` executor (just `clone_repo`)
or the `conda_python_environment` executor (everything else), matching every other workflow in
this repository. There is no Docker or remote/SSH target here — the repo ships no Dockerfile,
and no example workflow in this repo currently exercises `ssh`/`slurm` targets. Data flows
between tasks purely through file/folder outputs wired via `edges:`, so a task only starts once
its upstream artifacts exist.

## Input / Output

**Input**: none — the workflow is self-contained; it clones its own source repo and downloads
its own datasets (Pile shard, Alpaca, Dolly, GSM8K) from Hugging Face.

**Output**:
- `ckpts/base_pretrained.pt`, `ckpts/sft.pt` — self-describing checkpoints (embed the resolved
  model config, training step, and metrics, so no separate architecture file is needed to load
  them for eval/inference).
- `logs/pretrain.jsonl`, `logs/sft.jsonl` — one JSON record per logged training step.
- `logs/stage_table.jsonl` — GSM8K accuracy row for the SFT checkpoint.

## Parameterization

- **Model/step-count scale**: `train_pretrain`/`train_sft` load
  `configs/smoke/{pretrain,sft}.json` from the cloned repo — a tiny model
  (`n_embed=64, n_head=4, n_blocks=2`, `vocab_size=256`) trained for ~10-20 steps, sized to run
  on a single local CPU/GPU in minutes. To train the repo's default ~400M-param model, change
  `--config` in the `train_pretrain`/`train_sft` commands to `configs/pretrain.json` /
  `configs/sft.json` — expect this to need a real GPU (24GB+) and hours-to-days of runtime; the
  repo's own defaults target 2×H100 with `torchrun`, which this workflow does not wire up.
- Any dataclass field on `PretrainConfig`/`SFTConfig`
  (`config/post_training_config.py` in the cloned repo) can be overridden by adding
  `--field value` to the relevant task's `command:` — e.g. `--lr`, `--batch_size`,
  `--train_steps`, `--use_wandb true --wandb_project ...`.
- `prepare_pretrain_train`'s `--num_shards` (currently `1`) controls how much Pile text is
  pulled for pretraining.

## References

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) — source
  repo cloned by this workflow.
- [horus-runtime](https://github.com/temple-compute/horus-runtime) — workflow engine and plugin framework.
- [horus-environments](https://github.com/temple-compute/horus-environments) — horus plugin for conda-based Python environments.
