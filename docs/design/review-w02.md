# Review: W-38 `workflows/omsf/w02-openadmet-cyp3a4`

Branch `chdominguez/omsf-w02-admet` at `8f3db12`, diffed against
`feat/omsf-workflows` (`c1535fc`). Checked against
`docs/plans/omsf-workflows.md` sections 1, 3 and 4. The review is read-only:
no workflow code was changed.

## What was checked

- `make_recipes.py --selftest` and `models.py --selftest` pass, both in the
  workflow env and (`models.py`) with plain system `python3`.
- `horus sanitize workflow.yaml -o <tmp> -y` under horus-runtime 0.6.7 (the
  tc-os venv) and 0.7.0 (what `uv sync` resolves today) reports "No root
  inputs to promote" and writes no file. The CI script
  `.github/scripts/check_sanitized.py` prints `clean workflow.yaml`.
- Every YAML field exists in the installed sources: `conda_python_environment`
  (`conda`, `environment_file`, `environment_dir`, `env`), `slurm`
  (`inner`, `partition`, `account`, `ntasks`, `cpus_per_task`, `mem`, `gres`,
  `time_limit`), `horus_map` (`over.input_id`, `over.as`, `max_concurrency`),
  `choice` artifact, `python_script` runtime. All 9 edges are present, and
  every task input has an edge.
- The upstream CLI matches `openadmet {anvil,compare,predict} --help` from the
  installed openadmet-models 0.2.0: every flag the workflow passes exists, and
  `--report` takes a BOOLEAN. Tag `v0.2.0` resolves to `cdf3e9f7`, as the
  README says. The `ghcr.io/openadmet/openadmet-models` image exists with
  `main` as its only tag.
- Licenses (GitHub API): openadmet-demos, openadmet-models, data-catalogs and
  molfeat are all Apache-2.0. The README credit section is correct. No
  notebook code is copied: the cleaning is the four-line cell 13 logic,
  rewritten, and the recipes are generated, with a credit header.
- The full-profile recipes were compared with upstream
  `showcase/anvil_lgbm-cv.yaml` and `showcase/chemprop/anvil_recipe.yaml` at
  `8b2c5f34`.
- The skip_if_complete semantics were read in `horus_task.py`. A task skips
  only if its outputs exist *and* a manifest written after a successful run
  matches the input/config fingerprint, so a crashed run never looks
  complete. The map (`map.py`) also removes slots left from an earlier, larger
  expansion. The `fetch_data` `.part` + `mv` pattern is correct.
- I reproduced the profile-switching behaviour with a trimmed copy of the
  workflow (`make_recipes` only, the same conda env, horus 0.7.0).
- Smoke re-run: see the last section.

## Findings

Counts: 1 blocker, 4 major, 14 minor. Findings marked (cr) came from, or were confirmed by, the `/code-review high` pass over the diff.

### Blocker

**B1. (cr) Full profile: Chemprop cannot use the GPU, because the env has a
CPU-only PyTorch.**
`conda_env.yaml:26` (`pytorch=2.14.1`), `scripts/make_recipes.py:77`
(`accelerator: gpu`).
The env built by the smoke run has
`pytorch-2.14.1-cpu_mkl_py312_*` and `libtorch-...-cpu_mkl_*`, and
`torch.version.cuda` is `None`. conda-forge picks the CUDA build only when
the solving host has the `__cuda` virtual package. The env is built by the
first conda task (`make_recipes`, `target: *local`, so the login node or
laptop, with no GPU). The executor then reuses the env when the directory
exists, without checking its contents. So when the full profile's train map
runs on the `_gpu` Slurm target, the Chemprop clone gets a CPU-only torch and
Lightning fails on `accelerator: gpu`. The default map
`on_item_failure: fail` then fails the whole map, so the GPU demo that
section 3 promises cannot work as shipped.
Fix: pin a CUDA build in `conda_env.yaml` (for example
`pytorch=2.14.1=cuda*` or `pytorch-gpu=2.14.1`), and tell users to build on a
non-GPU host with `CONDA_OVERRIDE_CUDA=12.9`. Or give `train` its own
`_conda_gpu` anchor with its own `environment_dir`, so that env is built on
the GPU node. Then state in the README which one is meant.

### Major

**M1. Switching the profile by editing `value:` in `workflow.yaml` is
silently ignored after the first run.**
`README.md:112-115`, `workflow.yaml:55`.
A root value artifact is materialized to `params/profile.txt` only when that
file does not yet exist (`horus_builtin/artifact/value.py`, `materialize`:
"once the file exists it is left alone"). I reproduced this: run with
`value: full`, change it to `value: smoke`, re-run. The result is "Skipping
task make_recipes. Already complete", and `params/profile.txt` still says
`full`. The file lands next to `workflow.yaml`, not under
`horus_workflow_results/`. So the documented step "set the `profile`
artifact to `full` (edit `value:` in `workflow.yaml` ...)" does nothing for
anyone who ran the smoke profile first, which the README tells them to do.
Fix: document `printf full > params/profile.txt` (or deleting that file)
as the way to switch from the CLI, keep "pick it in the UI" for tc-os, and
mention that `params/` is run state: it is not in `.gitignore`, so every
run leaves `?? .../params/` in `git status`. Add it to `.gitignore`. (cr) A
related trap: `value: smoke` is copied onto the `profile` inputs of
`make_recipes` (`workflow.yaml:105`) and `predict` (`workflow.yaml:210`).
Those copies are overwritten by the root value through the edge, so a user
who edits the nearest `value:` changes nothing. Say "the root `artifacts:`
entry" in the README, or drop the `value:` from the task inputs if sanitize
allows it.

**M2. `make_recipes` leaves stale recipe slots behind, so switching full
to smoke trains all five models, including GPU Chemprop.**
`scripts/make_recipes.py:115-123`.
`write_all` does `mkdir(exist_ok=True)` and never removes model folders that
the current profile does not list. Horus does not clear a plain task's folder
output before a re-run either (only `reset`, which `horus run` never calls,
and only the map prunes stale slots). I reproduced this: profile `full`
writes 5 slots, then `printf smoke > params/profile.txt` and a re-run writes
lgbm and rf, but `recipes/` still holds `catboost`, `chemprop`, `lgbm`, `rf`
and `xgboost`. The train map then fans out over all 5 on the local CPU target
with full-profile recipes (5x5 CV, `n_jobs: -1`), and `chemprop`
(`accelerator: gpu`) fails, which fails the run. Smoke to full is unaffected.
Fix: `shutil.rmtree(out, ignore_errors=True)` before `out.mkdir(...)` in
`write_all`, and a selftest that writes full then smoke into the same folder
and asserts there are 2 children.

**M3. The container swap in the README fails as written: `horus-docker` is
not a dependency.**
`README.md:88-98`, `pyproject.toml:4-8`.
The `.venv` that `uv sync` creates has only `horus-runtime`,
`horus-environments` and `horus-slurm`, so `kind: docker` is an unknown
kind. The field names in the snippet are valid against horus_docker 0.3.5
(`image: str`, `gpus: str | None`), and `python_script` is allowed because
`PythonScriptRuntime` subclasses `CommandRuntime`. But the snippet also drops
the `env:` block, so `OADMET_NO_RICH_LOGGING=1` and `MPLBACKEND=Agg` are lost
(docker supports `env:`). I did not check whether the image's default
`python` has pandas and pyyaml for the python_script tasks.
Fix: tell users to add `horus-docker` to `pyproject.toml` (or add it as an
optional extra), and keep the `env:` block in the snippet.

**M4. No Singularity/Apptainer swap, though the GPU path is Slurm.**
`README.md:88-98`.
The full profile only makes sense on Slurm, and Docker is rarely available on
HPC nodes. Plan section 1 lists `singularity{image, exe: apptainer, nv: true}`
for exactly this case. Every field is valid in horus_singularity 0.3.2
(`image`, `exe`, `nv`, `env`, `binds`).
Fix: add a second snippet: `kind: singularity`,
`image: docker://ghcr.io/openadmet/openadmet-models:main`, `exe: apptainer`,
`nv: true`, the same `env:`, plus the `horus-singularity` dependency.

### Minor

**m1. "Library-default hyperparameters except the tree count" is not true
for xgboost and catboost.**
`README.md:173-174`, `scripts/make_recipes.py:34-35`.
Both also set `learning_rate: 0.05` (xgboost's default is 0.3, and catboost
picks its own rate automatically), plus `random_state` on rf, xgboost and
catboost.
Fix: either drop the overrides or describe them ("lgbm's learning rate and
tree count").

**m2. The full profile differs from upstream in small ways that are not
documented.**
`scripts/make_recipes.py:50-57, 65`.
`_cv_eval` adds `random_state: 42` to the sklearn CV (upstream lgbm has none)
and `max_val: 10` / `min_val: 3` to the Chemprop CV (upstream has neither).
The Chemprop recipe uses `dropna: true` (upstream `false`) and the eval title
"pAC50" (upstream "LogAC50"). The upstream showcase also compares a third,
multitask model (`OPENADMET_LOGAC50_cyp3a4`, notebook cell 18) that the port
leaves out. These are all reasonable choices.
Fix: add one README line under Implementation Notes listing the deviations,
and say the multitask model is out of scope.

**m3. (cr) `n_jobs: -1` is not "the whole Slurm allocation" for every library.**
`README.md:120-121`, `scripts/make_recipes.py:46, 89`.
joblib (featurizers) and libgomp (lightgbm, xgboost) follow the cgroup or
affinity mask. catboost's `thread_count: -1` uses the host's core count, so
on a shared GPU node with `cpus_per_task: 8` it oversubscribes.
Fix: in the full profile, set n_jobs to the `_gpu` anchor's
`cpus_per_task` (8), or read `SLURM_CPUS_PER_TASK` in the recipe step, and
soften the README sentence.

**m4. (cr) `max_concurrency: 2` limits the full run on Slurm to 2 jobs at a
time.**
`workflow.yaml:136`.
With 5 clones on Slurm, Chemprop (hours) can wait for a free slot behind
the tree models. That is not a correctness problem, but the README calls the
target swap "the only edit".
Fix: mention raising it to 5 for the full Slurm run, or set it to 5 (local
smoke has only 2 clones anyway).

**m5. Pin openadmet-models by commit, not tag.**
`conda_env.yaml:49`.
`@v0.2.0` is a mutable ref. molfeat on the line above is pinned by SHA.
Fix: `@cdf3e9f7de9ae6b30d13a28c68e20d3b2e651498` (keep the tag in the
comment).

**m6. The quick start is missing the `cd` into the workflow folder.**
`README.md:41-50`.
`uv sync` has to run where this folder's `pyproject.toml` is. 31 of the 40
workflow READMEs in the repo start the block with `cd workflows/...`.
Fix: add `cd workflows/omsf/w02-openadmet-cyp3a4`. Also list `micromamba`
as a prerequisite inside the block, since the run fails without it.

**m7. The DAG differs from plan section 3.**
`workflow.yaml:256-292`.
The plan has `compare → predict`. The workflow runs `compare` and `predict`
in parallel from `train`, because `predict` picks the best model itself from
the CV JSON. This is an improvement (no data dependency), but the plan and
the README pipeline diagram should agree.
Fix: none in code. Note it in the plan or the PR description.

**m8. The smoke `predict` leaks a temp directory.**
`scripts/models.py:161-162` (`tempfile.mkdtemp()`).
It is never removed. It holds a 2000-row CSV per run.
Fix: write the head file into the task's working directory (cwd), or use
`TemporaryDirectory()` around `run(...)`.

**m9. `models.py --profile` defaults to `full`.**
`scripts/models.py:144`.
The workflow always passes `--profile`, but someone running the script by
hand gets the slow path by default, while the workflow default is smoke.
Fix: make it `required=True`, as `make_recipes.py` effectively does.

**m10. (cr) Editing `conda_env.yaml` does not rebuild the env.**
`workflow.yaml:10-14`.
`conda_python_environment` reuses the prefix whenever it exists. The task
fingerprint includes `conda_env.yaml`, so tasks re-run, but they run on the
old packages. The same rule is what makes B1 stick.
Fix: one README line: "after changing `conda_env.yaml`, delete
`horus_workflow_results/.horus_conda_env`" (or set `recreate: true` once).

**m11. (cr) `write_csv` crashes on an empty row list.**
`scripts/models.py:94` (`rows[0]`).
If every prediction is empty, `top_predictions` returns `[]` and `report`
raises IndexError after `metrics.csv` is already written. The task then
fails (no manifest), so this does not corrupt the cache, but the error is
unhelpful.
Fix: `sys.exit("no predictions in ...")` when the list is empty.

**m12. (cr) `best()` has no NaN guard.**
`scripts/models.py:41-42`.
A NaN mean (for example a degenerate fold for spearmanr or ktau) makes
`max()` depend on row order, so the wrong model can be picked and marked
`best`.
Fix: skip NaN means, or raise if the selection metric is NaN for every
model.

**m13. (cr) Argument validation is incomplete.**
`scripts/models.py:151`.
`report` without `--predictions`/`--top-out`, and `predict` without
`--compounds`, crash with a TypeError, or in full mode pass the literal
`None` to `openadmet predict`. This only matters for manual use; the workflow
always passes them.
Fix: check the required flags per mode next to the existing `ap.error`.

**m14. `horus_slurm.probe` fails to load on every run.**
`pyproject.toml:7`.
Every `horus` invocation in the uv venv logs `ERROR Failed to load plugin
horus_slurm.probe: No module named 'horus_resource_monitor'` (seen during
sanitize). It is harmless, but it is an ERROR line in a demo log.
Fix: depend on `horus-slurm[resource-monitor]` if that extra exists, or
match whatever the other Slurm workflows in the repo do.

Not kept from the code-review pass: a possible race on env creation by two
clones with `inner: ssh`. Plain `inner: local` is what is shipped and
documented, and there `make_recipes` always builds the env first.

## Not issues (checked)

- `rm -rf ${trained}/model` plus the `{ ...; }` grouping is POSIX `/bin/sh`
  (the conda executor runs `micromamba run -p ... /bin/sh -c`). There is no
  `pipefail`, so the final `grep | tail` cannot fail a successful train.
- `environment_dir: ../../.horus_conda_env` resolves to the shared env for
  plain tasks (`<task>/<run>/`) and map clones (`train[0]/<run>/`).
- `partition: ""` and `account: ""` are skipped by horus_slurm
  (`if self.partition:`), so the `_gpu` anchor works on the default partition.
  The anchor's `cpus_per_task`, `mem` and `gres` override the task's smoke
  `resources` (`resolve_resources`), as intended. Moving to Slurm is a
  one-field change (`target: *gpu`), apart from B1.
- `collect()` sorts by label. Slots are zero-padded by the map, and there are
  at most 5 models. `n_folds` reads `value`, which is present in the real
  `cross_validation_metrics.json`.
- The predictions column name `OADMET_PRED_openadmet-chembl_OPENADMET_LOGAC50`
  matches the real output.
- The parquet download is a real Parquet file (`PAR1` magic, not an LFS
  pointer). The cleaned file has 4919 compounds, and the inference set has
  10,000 rows.

## Smoke re-run

I ran the quick start from a clean worktree (`uv sync && uv run horus run
workflow.yaml --no-tui`), limited to 4 cores with `taskset -c 0-3`. The env
was built cold.

- It passed (exit 0) in **7 min 3 s** wall time. Per task: fetch 0.7 s,
  make_recipes 62 s (including the env build), train 313 s (lgbm 219 s, rf
  313 s), compare 21 s, predict 45 s, report 0.2 s. These match the README's
  runtime section.
- It picked rf, with mean CV R2 0.514 against 0.451 for lgbm. That matches
  the README and the author's run.
- A second run skipped all 6 tasks in 0.1 s, so `skip_if_complete` works.
- Afterwards `git status` showed `?? workflows/omsf/w02-openadmet-cyp3a4/params/`,
  which confirms M1's `.gitignore` point.
- The compare log prints seaborn `ci` deprecation warnings from upstream.
  They are harmless.
