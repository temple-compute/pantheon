# W-01 · Boltz-2 Virtual Screening

![Status: alpha](https://img.shields.io/badge/status-alpha-orange)
![Domain: Drug Discovery](https://img.shields.io/badge/domain-drug--discovery-blue)
![GTM: Tier 1](https://img.shields.io/badge/GTM-Tier%201-green)

## Overview

Given a target protein and a library of candidate ligands, this workflow predicts
binding structure **and** affinity for each protein–ligand pair with
[Boltz-2](https://github.com/jwohlwend/boltz), then returns a ranked shortlist.
Boltz-2 (MIT/Recursion, 2025) gives affinity prediction at a fraction of the cost
of classical free-energy perturbation, making large virtual screens tractable.

The point on Horus: the expensive GPU only runs **one** stage. Cheap CPU prep and
ranking run locally; the GPU stage runs on a remote box (or in a container, or
both) and Horus moves the data across the boundary automatically. Swapping where
and how the GPU stage runs is a one-line config change.

**Target users:** computational chemists, pharma/biotech and academic drug-discovery teams.

---

## Pipeline

```
prep (local, CPU)          target.fasta + ligands.smi ──► boltz_inputs.tar.gz
   │   LocalToSSH transfer (automatic)
predict (SSH GPU box)      boltz predict (container)   ──► predictions.tar.gz
   │   SSHToLocal transfer (automatic)
rank (local, CPU)          parse affinity + confidence ──► top_hits.csv
```

| Stage | Target | Engine | What it does |
|-------|--------|--------|--------------|
| `prep` | local | python | One Boltz-2 input YAML per ligand (protein + ligand SMILES + affinity), tarred. |
| `predict` | SSH GPU box | docker / singularity / baremetal | `boltz predict` over the bundle; tars the output. |
| `rank` | local | python | Joins `affinity_*.json` + `confidence_*.json` → ranked CSV. |

Cross-stage artifacts are **single tar files** on purpose: Horus SSH transfer is
file-based, so a tarball is what crosses the wire.

The DAG order and the transfer source for each input are wired by **explicit
`WorkflowEdge`s** in `run.py` (`prep → predict → rank`); the runtime resolves
dependencies from those edges, not by inferring them from artifact ids.

---

## What this demonstrates (the Horus value props)

- **SSH staging** — `prep`'s output is pushed to the GPU box and `predict`'s output
  is pulled back, with no manual `scp`. (`horus-ssh` transfer strategies.)
- **Switch execution engine** — `engine: docker | singularity | baremetal` in
  `config.yaml` is the only change to move between container runtimes or bare metal.
- **Switch location** — `predict_target: ssh | local` moves the GPU stage between a
  remote box and your machine. Nothing else changes.
- **Resume** — a stage is skipped when its output already exists; re-running only
  recomputes what is missing.

---

## Quick start

```bash
cd workflows/drug-discovery/w01-boltz2-virtual-screening

# 0. Build the image on the GPU host (one time)
docker build -t boltz2:latest -f containers/boltz2.Dockerfile .

# 1. Configure
cp config.example.yaml config.yaml
$EDITOR config.yaml          # ssh host, engine, image, input paths

# 2. Run (live TUI with task progress, DAG, and logs)
python run.py                # or: python run.py path/to/config.yaml
```

Outputs land in `out_dir/`: `boltz_inputs.tar.gz`, `predictions.tar.gz`, and
`top_hits.csv` (ranked best-first).

**Requirements:** the orchestrator needs `horus-runtime` and `horus-ssh`
installed; the GPU box needs the chosen engine (or `boltz` on `PATH` for
`baremetal`) and an NVIDIA runtime.

---

## Inputs / Outputs

**Inputs**
- `target.fasta` — protein target (first record is used).
- `ligands.smi` — one `SMILES [name]` per line; `name` becomes the ranked-output id.

**Output** — `top_hits.csv`:

| column | meaning |
|--------|---------|
| `rank` | 1 = best |
| `ligand` | ligand id from `ligands.smi` |
| `affinity_probability_binary` | Boltz-2 probability the ligand binds (primary sort, desc) |
| `affinity_pred_value` | Boltz-2 predicted affinity (tie-break, asc) |
| `confidence_score` | structure confidence |

> Boltz-2 affinity is a reliable **ranking** signal, not a calibrated ΔG — the
> ordering is meaningful, the absolute numbers are not kcal/mol.

---

## Configuration

See `config.example.yaml`. Key knobs: `predict_target` (ssh/local), `engine`
(docker/singularity/baremetal), `image`, `boltz_args`, the `ssh:` block, input
paths, and `out_dir`. `config.yaml` is gitignored — never commit credentials.

---

## Files

```
run.py                      # driver: builds + runs the 3-task workflow from config.yaml (with TUI)
config.example.yaml         # copy to config.yaml and edit
scripts/prep.py             # stage 1 (stdlib only; --selftest)
scripts/rank.py             # stage 3 (stdlib only; --selftest)
containers/boltz2.Dockerfile
examples/                   # tiny target.fasta + ligands.smi fixture
```

`prep.py` and `rank.py` carry `--selftest` self-checks (no Boltz/GPU needed):

```bash
python scripts/prep.py --selftest
python scripts/rank.py --selftest
```

---

## Verify end-to-end

1. **Local smoke (no GPU/SSH):** put a `boltz` stub on `PATH` (or install the real
   one), set `predict_target: local`, `engine: baremetal`, and `python run.py`.
   Confirms the DAG, artifact substitution, tar round-trip, and ranking.
2. **SSH + container:** point `config.yaml` at a GPU box, `engine: docker`, and run.
   Confirms `boltz_inputs.tar.gz` is staged out and `predictions.tar.gz` pulled back.
3. **Switch demo:** flip `engine` docker→singularity and `predict_target` ssh→local
   — nothing else changes.

---

## Roadmap (needs runtime/plugin work — tracked as issues)

This `alpha` runs one library on one GPU target. The following are **not** built
here and depend on upstream features (tracked as issues):

- **GPU job-array fan-out** across many ligand batches — needs resource requests
  ([horus-runtime#90](https://github.com/temple-compute/horus-runtime/issues/90))
  and parallel fan-out
  ([horus-runtime#91](https://github.com/temple-compute/horus-runtime/issues/91)).
- **Docking refinement stage** (DiffDock / AutoDock-GPU) on the top hits — a
  second container + stage.
- **Slurm submission** for the GPU stage — target is a stub today
  ([horus-slurm#2](https://github.com/temple-compute/horus-slurm/issues/2)).
- **Recursive/folder transfer** over SSH — would drop the tarball workaround
  ([horus-ssh#6](https://github.com/temple-compute/horus-ssh/issues/6)).

---

## References

- [Boltz-2 GitHub](https://github.com/jwohlwend/boltz) · [paper](https://www.biorxiv.org/content/10.1101/2024.05.24.595648)
- [Horus runtime](https://horus.bsc.es) · `horus-ssh` plugin
