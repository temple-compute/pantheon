# OMSF workflows: port plan

## Context
OMSF's infra team (Open Force Field, OpenFE, OpenADMET) is evaluating Horus. Their pain is running one pipeline on Slurm, cloud GPUs and laptops without re-engineering it. We port 3 of their 16 directory workflows into native Horus workflows in `pantheon` as a demo (first ones due Sun 18 Oct 2026). Depth over breadth: real task decomposition, map fan-out, CPU and GPU steps on different targets, and a smoke profile that runs in minutes.

User decisions (verbatim answers):
- GPU smoke: "Local CPU, tiny sampling" (no GPU or Slurm on this host; the Slurm GPU run is documented and run later by the user)
- Env: "conda-forge pin + container swap"
- Scope: "RBFE + OpenADMET + OpenFF" (OpenFF gets dropped if it puts the first two at risk)

Research is done (3 agents: repo conventions, triage of all 16 entries, upstream CLI and env check against openfe v1.13.0 / openadmet-models v0.2.0 / openff-toolkit 0.19.0). Results are below.

## Step A: first commit on `feat/omsf-workflows`
Write `docs/plans/omsf-workflows.md` (the requested deliverable) from sections 1-6 below. Also add `workflows/omsf/README.md` (category index, modeled on `workflows/bioexcel_building_blocks/README.md`) and 3 rows in the root `README.md` (W-37, W-38, W-39; W-36 is the highest number in use). Doing this up front means engineers never touch shared files.

---
## 1. Conventions (verified against horus-runtime v0.6.7 + installed plugins)
- Layout: `workflows/<domain>/wNN-slug/` containing `README.md` (template in `CONTRIBUTING.md`, including a `## Quick start` section; first line `# W-NN · Title`), `workflow.yaml`, `pyproject.toml` (`requires-python>=3.13`, `horus-runtime`, plus `horus-environments` and `horus-slurm` as needed), `scripts/` (stdlib Python with a `--selftest` assert mode), and optionally `examples/` and `conda_env.yaml`. Repo license: MIT. Upstream code is MIT or Apache-2.0, and we install packages rather than copy code.
- YAML: `kind: horus_workflow`; top-level `_anchor: &x` blocks for executors and targets; `artifacts:`; tasks of `kind: horus_task` / `horus_map` with `inputs`, `outputs`, `resources{cpus,gpus,memory_gb,vram_gb,walltime}`, `executor`, `runtime{command | python_script(script,args,python)}`, `target`; `edges` (source `artifact-<id>` for root artifacts). CI (`sanitize-check.yml`) requires `horus sanitize`-clean YAML.
- Map: `kind: horus_map`, `over{input_id, as}`, one flat runtime per item, a folder iterates its sorted children, the single output is rebound per clone into one slot each, `max_concurrency` (default 8), `on_item_failure: fail|drop`. No gather task is needed: downstream consumes the output folder. Reference: `workflows/drug-discovery/w04-cmd/workflow.yaml`. Do not use the old `map:` sugar from `engine-showcases/w01` and `w03`; it was removed in runtime 0.6.
- Executors: `conda_python_environment{conda: micromamba, environment_file | channels+conda_requirements, environment_dir}`, `uv_python_environment`, `docker{image,gpus}`, `singularity{image, exe: apptainer, nv: true}`, `shell`.
- Targets: `local`; `slurm{inner: local, partition, account, qos, gres, time_limit, mem, cpus_per_task}` (falls back to task `resources`); `ssh`; `terraform` (cloud VM, extends ssh).
- Parameters: there are no profiles. Values are artifacts (`boolean`, `choice`, `number`, `string`) stored at a path; see w08's `use_msa`. We use a `choice` artifact `profile: smoke|full` that scripts read.
- Outputs: `.csv` and `.tsv` render as tables and `.html` as a live page. The Mol* HTML report pattern lives in `drug-discovery/w06-*/scripts/report.py`. Downloads use the `curl -fL --retry 3 -o X.part && mv X.part X` pattern from w03, so a partial file never counts as complete.

## 2. Triage (16 entries, sources in research notes)
| # | Entry | Proj | Type | Iface | Compute | Fan-out | Verdict |
|---|---|---|---|---|---|---|---|
|1|Export to AMBER/GROMACS|OpenFF|tutorial|nb|CPU s|weak|skip: conversion only|
|2|Sage ligand + Amber protein|OpenFF|tutorial|nb|CPU min|ligands|T2: overlaps #9|
|3|Conformer Energies|OpenFF|small script|CLI script|CPU min|molecules|T2 (backup T1)|
|4|Forcefield Modification|OpenFF|tutorial|nb|CPU min|param scan|T2|
|5|Inspecting SMIRNOFF Params|OpenFF|tutorial|nb|CPU s|none|skip|
|6|QCArchive Interface|OpenFF|tutorial|nb+net|I/O|records|skip: external server|
|7|SMIRNOFF Simulation|OpenFF|tutorial|nb|CPU min|molecules|T2|
|8|Virtual Sites Showcase|OpenFF|tutorial|nb|CPU|none|skip|
|9|OpenFF Toolkit Showcase|OpenFF|end-to-end MD tutorial|nb (Python API)|CPU/GPU, min|replicas|**T1 (3rd)**: decompose into scripts|
|10|PTM Prototype|OpenFF|prototype|nb|short MD|none|skip: alpha FF|
|11|Visualizations|OpenFF|tutorial|nb|none|none|skip|
|12|Partial charges CLI|OpenFE|CLI step|CLI|CPU min|ligands|**T1**, merged into #14 as prep|
|13|OpenFE Showcase|OpenFE|tutorial|API+CLI|GPU|edges|T2: same science as #14|
|14|RBFE with OpenFE CLI (TYK2)|OpenFE|real pipeline|CLI|plan CPU, quickrun GPU hrs/leg|legs x repeats|**T1 flagship**|
|15|OpenADMET Data Catalogs|OpenADMET|data catalog|intake/parquet|I/O|catalogs|T2: input source for #16|
|16|OpenADMET Showcase (CYP3A4)|OpenADMET|real pipeline|CLI (`openadmet anvil/compare/predict`)|CPU (LGBM), GPU (Chemprop)|model types|**T1**|

Your proposed Tier 1 holds up. One challenge to it: the OpenFF showcase is notebook-only with nglview, so it has to be decomposed into scripts. That is feasible but makes it the riskiest of the three, so it is ranked third.

## 3. Tier 1 designs

### W-37 `workflows/omsf/w01-openfe-rbfe-tyk2` (flagship)
DAG: `fetch_inputs → charge_ligands → plan_network → [map] quickrun (per leg) → gather → report`
| Task | What | How | Where |
|---|---|---|---|
|fetch_inputs|curl `tyk2_ligands.sdf` and `tyk2_protein.pdb` from OpenFreeEnergy/ExampleNotebooks at a pinned commit|shell|local CPU|
|charge_ligands|`openfe charge-molecules -M ligands.sdf -o charged.sdf -n ${cpus}` (AM1-BCC, ambertools)|conda openfe=1.13.0|local or Slurm CPU|
|plan_network|`scripts/plan.py`: thin openfe API glue. Mirrors `plan-rbfe-network` (Kartograf mapper, minimal spanning network). The CLI settings YAML cannot change sampling (only `mapper`, `network` and `partial_charge` keys exist), so a script is needed. smoke: 3 ligands → 2 edges → 4 legs, `protocol_repeats=1`, production about 20 ps, equilibration about 10 ps, fewer lambda windows (keep `n_replicas` equal to the window count). full: protocol defaults (3 repeats, 1 ns eq / 5 ns prod, 11 windows). Writes `transformations/*.json` and `ligand_network.graphml`|conda openfe|CPU|
|quickrun (horus_map over transformations/)|`openfe quickrun ${leg} -o ${out}/result.json -d ${out}/work`|conda openfe (container swap shown in README)|smoke: local CPU; full: `_gpu` Slurm anchor (`gres: gpu:1`), `resources.gpus: 1`|
|gather|`openfe gather ${results} --report ddg -o ddg.tsv` and `--report dg -o dg.tsv` (`--allow-partial` for smoke)|conda openfe|CPU|
|report|`scripts/report.py`: HTML with the ΔG/ΔΔG table, the network edges, and Mol* showing protein + ligands (w06 pattern)|shell python3 stdlib|CPU|
Outputs: `ddg.tsv`, `dg.tsv` (tables), `report.html` (Mol*), `ligand_network.graphml`.

### W-38 `workflows/omsf/w02-openadmet-cyp3a4`
DAG: `fetch_data → make_recipes → [map] train (per model) → {compare, predict} (parallel) → report`
| Task | What | Where |
|---|---|---|
|fetch_data|curl the ChEMBL35 CYP3A4 IC50 aggregated parquet (data-catalogs, pinned commit) and `compounds_for_inference.csv` (openadmet-demos, pinned)|local|
|make_recipes|`scripts/make_recipes.py` writes one anvil CV recipe per model, based on upstream `anvil_lgbm-cv.yaml`. smoke: lgbm + rf, 2x2 CV, fewer estimators. full: lgbm, rf, xgboost, catboost, chemprop with upstream 5x5 CV|CPU|
|train (horus_map over recipes/)|`openadmet anvil --recipe-path ${recipe} --output-dir ${out}`|smoke local CPU; full on a Slurm GPU anchor (needed for chemprop)|
|compare|`openadmet compare --model-stats-fns <each cross_validation_metrics.json> --labels ... --output-dir comparisons --report True`|CPU|
|predict|`openadmet predict --input-path compounds_for_inference.csv --input-col OPENADMET_CANONICAL_SMILES --model-dir <best> --output-csv predictions.csv --accelerator cpu` (best model = highest mean CV R², picked by a short script)|CPU|
|report|`metrics.csv` plus top predictions table|CPU|
Env: conda env file (conda-forge deps from upstream `devtools/conda-envs/openadmet-models.yaml`, plus `openadmet-models==0.2.0`). Set `OADMET_NO_RICH_LOGGING=1`.

### W-39 `workflows/omsf/w03-openff-protein-ligand-md`
DAG: `fetch_inputs → build_system → parameterize → [map] simulate (per replica seed) → analyze`
- fetch: `5tbm_prepared.pdb` and `PT2385.sdf` from openff-toolkit tag 0.19.0.
- build_system: PDBFixer solvation (1 nm padding, 0.15 M), insert the ligand and remove clashing waters, write `topology.json`.
- parameterize: `ForceField("openff-2.3.0.offxml","ff14sb_off_impropers_0.0.4.offxml")`, `create_interchange`, export OpenMM `system.xml` and `complex.pdb`, write `replicas/<i>/` slots (smoke 2 replicas, full 3).
- simulate (map): OpenMM minimize + Langevin 300 K, 2 fs. smoke: 2.5k steps (5 ps); full: upstream-like longer run; DCD output. CPU locally, GPU target via one-field swap.
- analyze: mdtraj RMSD per replica (`rmsd.csv`), `final_frame.pdb`, and `report.html` with Mol*.
- Env: conda with `openff-toolkit=0.19.0`, `openff-interchange=0.5.5`, `openmm=8.6.1`, pdbfixer, mdtraj. There is no official container.

## 4. Test plan
1. Every script has `--selftest` (asserts, tiny fixture) and runs without the heavy deps where possible.
2. `horus sanitize workflow.yaml` stays clean (this is the CI check).
3. Local smoke: `uv sync && uv run horus run workflow.yaml --no-tui` with `profile=smoke` (W-37 CPU target: under about 45 min; W-38: under 10 min; W-39: under 15 min). Then re-run to confirm `skip_if_complete` skips everything.
4. Slurm: the user sets `partition` and `account` in the `_gpu` anchor and switches the map target to it. This is documented in the README and not run by the team (no cluster available).

## 5. Gaps and open questions
- No profile mechanism in Horus; we use a `choice` artifact. A map target cannot be chosen per item, so mixed CPU and GPU models in one map are not possible (full W-38 runs the whole map on the GPU target).
- Horus runtime bug (value artifacts): `${profile}` renders the root `value:`, but the skip_if_complete fingerprint hashes the materialized `params/profile.txt`, which `ValueArtifact.materialize` writes only when missing. Editing `value:` alone therefore re-uses stale outputs. Workaround documented in every README: edit `value:` and `rm params/profile.txt`. Fix upstream: fingerprint the authored value, or re-materialize when it changes.
- No Kubernetes or Modal target. Cloud GPU means `terraform` or `ssh` targets, which are documented but not exercised.
- Open: whether the openadmet-models v0.2.0 CLI matches the showcase (which installs `main`); the engineer verifies and pins a commit if not. Whether openfe 1.13.0 accepts a reduced `lambda_windows`. Whether tc-os import still rejects folder artifacts (w04-cmd works around it with a tarball). The duplicate W-numbers in the root README are not fixed here.

## 6. Ordered checklist (estimates)
1. Step A commit (plan doc, category README, root README rows): 0.5 h, coordinator
2. W-37 RBFE: 5-6 h · W-38 OpenADMET: 3-4 h · W-39 OpenFF: 4 h (in parallel)
3. Review and fix: 1-2 h
4. E2E smoke of all 3: 1-2 h
5. Merge the WP branches into `feat/omsf-workflows`. No push.

---
## Team execution (Orca, team-of-agents skill)
- `orca worktree create` for the feature on branch `feat/omsf-workflows`; Step A is committed there by me; `orca orchestration run-create`.
- Waves 0, 0b and 1 (research, PM, design) are already covered by this plan. A UX designer and frontend architect are skipped because the workflows have no UI.
- Wave 2, 3 engineers in parallel (`worker-start --worktree new-top-level --base-branch feat/omsf-workflows --agent claude`), each owning only `workflows/omsf/wNN-*/`: `omsf-w01-rbfe`, `omsf-w02-admet`, `omsf-w03-openff`. Each spec contains its section 3 design, the conventions, the user decisions and the common rules (GPG-signed commits, no attribution, no push), and requires a real local smoke run plus the log tail as evidence. Worker setup: `uv sync` in the workflow folder; micromamba is at `~/.local/bin`.
- Wave 3, read-only reviewers: correctness (`/code-review high`) and Horus-schema/convention conformance. Then one fix worker, at most 2 rounds.
- Wave 4: one E2E worker re-runs all 3 smoke profiles from the merged branch and checks the incremental skip.
- Monitoring: a background poll loop over `worker-list`, answering `ask` messages promptly.
- Final report to the user: per workflow, outcome, evidence and remaining blockers.
