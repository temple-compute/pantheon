# W-29 · Tiny LLM From Scratch - TinyStories Pretrain & Sample

![Domain: AI](https://img.shields.io/badge/domain-ai-blue) ![horus-runtime](https://img.shields.io/badge/horus--runtime-workflow-green)

<img width="1080" height="929" alt="train-llm-cropped" src="https://github.com/user-attachments/assets/6b4a80ef-bf49-473d-9e85-c76f69373673" />

## Overview

A fast, small-data companion to [W-28](../w01-train-llm/README.md): pretrains the same
from-scratch decoder-only Transformer, but on
[TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories) (short, simple
GPT-generated children's stories, a couple hundred MB) instead of the Pile (~900GB). It exists
for people who want to see a from-scratch LLM learn something legible in minutes on a laptop,
without the Pile's disk/bandwidth requirements. It skips instruction tuning and eval entirely.
The deliverable is a pretrained checkpoint plus a sample generation proving it learned to
continue a story prompt.

## Pipeline

```
clone_repo (local)
   │
   ├─► prepare_tinystories_train / prepare_tinystories_val  ──► tinystories_{train,val}.h5
   │        └─► train_pretrain_tiny (local)                 ──► tinystories_pretrained.pt
   │                 └─► sample_story (local)                ──► tinystories_sample.txt
```

## Quick start

```bash
# Install the horus-runtime and plugins (one time)
uv sync

# You can install UV with this command if you don't have it yet:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Otherwise, you can install the horus-runtime and plugins with pip:
# pip install horus-runtime horus-environments

# Run the workflow
uv run horus run workflow.yaml
```

Outputs land under `workflow_results/`: `repo/` (the cloned training repo), `data/` (tokenized
TinyStories), `ckpts/tinystories_pretrained.pt` (checkpoint), and
`samples/tinystories_sample.txt` (a greedy continuation of "Once upon a time,").

## Tools & Dependencies

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) (cloned at
  runtime by `clone_repo`). Pure PyTorch, no `transformers`/`trl`/`peft`. Only
  `scripts/pretrain_base.py` and `scripts/chat.py` are used from it.
- [TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories). Downloaded via the
  `datasets` library.
- `scripts/prepare_tinystories.py` (this workflow's own script, not from the cloned repo),
  tokenizes TinyStories with `tiktoken` into the same flat-token HDF5 layout
  (`data_loader/data_loader.py`'s `{"tokens": int32[N]}`) that `pretrain_base.py` expects.
  The cloned repo's own `scripts/prepare_pretrain_data.py` is hardcoded to the Pile, so this
  workflow can't reuse it directly.
- `torch`, `numpy`, `h5py`, `datasets`, `tiktoken`, provisioned via `conda_env.yaml`
  (micromamba) by the `conda_python_environment` ([horus-environments](https://github.com/temple-compute/horus-environments)) plugin executor.

## Horus Configuration

Every task runs `target: {kind: local}`, either on the bare `shell` executor (just `clone_repo`)
or the `conda_python_environment` executor. `prepare_tinystories_{train,val}` take `repo_dir` as an input purely to give
every task in this workflow one shared root (`clone_repo`), even though the tokenizer script
itself doesn't read from the checkout.

## Input / Output

**Input**: none. Self-contained; clones its own source repo and downloads TinyStories from
Hugging Face.

**Output**:
- `ckpts/tinystories_pretrained.pt`. Self-describing checkpoint (embeds the resolved model
  config, training step, and metrics).
- `logs/pretrain.jsonl`. One JSON record per logged training step.
- `samples/tinystories_sample.txt`. A greedy, raw (non-chat-template) continuation of
  "Once upon a time," from the trained model.

## Parameterization

- **Dataset size**: `prepare_tinystories_train`/`prepare_tinystories_val`'s `--max_docs` (default
  20,000 / 2,000) caps how many stories get tokenized, raise it (or drop the flag entirely) for
  more data at the cost of longer prep time. Full TinyStories is ~2.1M train stories.
- **Model/step-count scale**: `train_pretrain_tiny` loads `configs/smoke/pretrain.json` from the
  cloned repo (`n_embed=128, n_head=4, n_blocks=2, context_length=256`, `train_steps=20`) — a
  small model trained briefly, sized to run on a laptop CPU/GPU in minutes. Any
  `PretrainConfig` field (`config/post_training_config.py` in the cloned repo) can be overridden
  by adding `--field value` to the task's `command:`, e.g. `--train_steps 500 --lr 3e-4`, for a
  more thoroughly trained tiny model.
- `sample_story`'s `--prompt`/`--max_new_tokens`/`--temperature`/`--top_p` control the sample
  generation.

## Implementation Notes

- TinyStories tokens still use `tiktoken`'s `r50k_base` (50,257 vocab), matching the smoke
  config's `vocab_size=50304` (padded up) inherited from `configs/smoke/base.json`, no vocab
  mismatch with the cloned repo's model/tokenizer.
- `sample_story` uses `--raw` (base-model continuation) since this workflow never runs SFT: the
  checkpoint has no instruction-following behavior, only next-token continuation.

## References

- [train-llm-from-scratch](https://github.com/FareedKhan-dev/train-llm-from-scratch) — source
  repo cloned by this workflow.
- [TinyStories dataset](https://huggingface.co/datasets/roneneldan/TinyStories) ·
  [paper](https://arxiv.org/abs/2305.07759) — short, simple GPT-generated children's stories.
- [horus-runtime](https://github.com/temple-compute/horus-runtime) — workflow engine and plugin framework.
- [horus-environments](https://github.com/temple-compute/horus-environments) — horus plugin for conda-based Python environments.
