# Review: W-37 `workflows/omsf/w01-openfe-rbfe-tyk2`

Branch reviewed: `chdominguez/omsf-w01-rbfe` at `2bcf848`, diff against `feat/omsf-workflows`.
Plan: `docs/plans/omsf-workflows.md` sections 1, 3, 4. Read-only review; no workflow code changed.

Paths below are relative to `workflows/omsf/w01-openfe-rbfe-tyk2/`.

## Summary

| Severity | Count |
|---|---|
| blocker | 0 |
| major | 3 |
| minor | 9 |

The full profile is the `openfe plan-rbfe-network` default, checked against the installed
openfe 1.13.0 source. Sanitize is clean, edges are complete, and every YAML field exists in
horus-runtime v0.6.7 and the installed plugins. The three major findings are all in the `quickrun`
map body: a leg killed by Slurm cannot be re-run without manual cleanup, a slot that re-runs for
a different leg keeps the old leg's result JSON, and the openfe work directory (GBs of
trajectories in full) sits inside the map output that Horus fingerprints and transfers.

## Findings

### M1 (major) `workflow.yaml:205-208`: an interrupted leg cannot be re-run

**Problem.** `openfe quickrun` writes `work/quickrun_cache/dag-cache-<hash>.json` when it
starts and deletes it only when it finishes (on success or a unit failure; see
`openfecli/commands/quickrun.py`). If the job is killed (Slurm `TIMEOUT` at the 24 h limit,
preemption, Ctrl-C, OOM), the cache file stays. Horus has no manifest for the clone, so the next
`horus run` re-runs it into the same slot, and quickrun then exits at once with "Transformation has
been started but is incomplete. Please remove ... or resume execution using the --resume flag".
Every later run fails the same way until someone deletes the file by hand. This is the main
failure mode of the full profile (18 GPU legs of many hours each).

**Fix.** Add `--resume` to the quickrun command. With no cache it starts fresh (it only prints a
note). With a cache it resumes the finished units. The cache key hashes the output path and the
transformation, so a cache from a different leg is never reused.

### M2 (major) `workflow.yaml:205-208`: a re-run slot keeps the previous leg's result JSON

**Problem.** Map slots are named by index (`0..3` in smoke, `00..17` in full). `MapTask` keeps
slots that still exist ("their contents are what lets an unchanged clone skip") and a re-run
`HorusTask` clone does not clear its output before running (`HorusTask._run` / `BaseTask.run`
only call `reset()` on an explicit workflow reset). When a slot re-runs for a *different*
transformation, quickrun writes `${legs}/<new stem>.json` next to `<old stem>.json`.
`openfe gather` walks `legs/` recursively and picks up both, so ddG/raw/dG silently mix the old
and new networks (or gather errors on duplicate edges). Ways to hit it: edit `SMOKE` in
`scripts/select_ligands.py` to another 3 ligands, follow the README hint "to run your own
series, replace `fetch_inputs`" with a series whose leg count has the same number of digits
as the previous run's, or change a mapper setting so the edges change. Smoke to full is not affected (slot width goes
from 1 to 2 digits, so the old slots are pruned).

**Fix.** Write every leg's result to one fixed name, `-o ${legs}/result.json`, so a re-run
always overwrites it (gather reads the leg identity from the JSON content, not the file name).
Alternatively `rm -f ${legs}/*.json` before quickrun. Either keeps `work/` for `--resume` (M1);
the quickrun cache key includes the transformation, so a stale cache is never reused.

### M3 (major) `workflow.yaml:207`: the openfe work directory is inside the map output

**Problem.** `-d ${legs}/work` puts trajectories, checkpoints and `*_db.json` files into the
`legs` folder artifact. Horus fingerprints that folder as `gather`'s input on every run
(`is_complete` digests inputs), transfers it when `gather` and `quickrun` are on different
targets, and side-uploads it; `openfe gather` also walks it recursively three times. A smoke
slot is already ~19 MB from 2 ps; a full complex leg (3 repeats x 11 replicas x 6 ns) is many
GB, times 18 legs, all to read 18 small result JSONs.

**Fix.** Keep the work directory out of the output. The clone's cwd is a fresh per-invocation
folder (`horus_workflow_results/quickrun[N]/<execution id>/`), so `-d work` would not survive for
`--resume` (M1); `-d ../work` gives a stable `quickrun[N]/work` outside the artifact. Update the README row for
`legs/<slot>/` and the Implementation Note about work dirs.

### m1 (minor) `README.md:87-91`: the reason given for `rm ... horus_workflow_results/results` is inaccurate

**Problem.** "the old per-leg slots in `results/legs/` would otherwise be gathered too" is not
what happens on a smoke-to-full switch: the map prunes slot names it no longer uses, and the
4 smoke slots (`0..3`) are not in the full set (`00..17`). Deleting `results/` is harmless but
not needed for that reason. The real stale-slot hazard is M2.

**Fix.** Once M2 is fixed, reduce step 1 to `rm params/profile.txt` (the known fingerprint
gap), or keep the `rm -rf results` and say it is a clean start rather than a slot fix.

### m2 (minor) `README.md:1-200`: README does not follow the CONTRIBUTING.md template exactly

**Problem.** `CONTRIBUTING.md` lists `## Horus Configuration`; the README has `## Pipeline` and
`## Running the full profile on Slurm GPUs` instead, and the executors/targets are only
described in prose. Everything else (title line, Overview, Compute Pattern, Tools &
Dependencies, Quick start, Input / Output, Parameterization, Implementation Notes, Open
Questions, References) is present.

**Fix.** Rename `## Pipeline` to `## Horus Configuration` (or add one with a short table:
executors `shell` / `conda_python_environment`, targets `local` / `_gpu` Slurm, map over
`transformations/`).

### m3 (minor) `README.md:105-124`: container swap misses two practical details

**Problem.** Verified: both images exist on ghcr (`1.13.0`, `1.13.0-apptainer`), and
`image`, `gpus`, `exe`, `nv` are real fields of `horus_docker` 0.3.5 / `horus_singularity`
0.3.2; both executors only accept `command` runtimes, as the README says, and both auto-mount
the artifact parent dirs. Not covered:
1. Docker runs as root by default, so `results/legs/*` and `results/*.tsv` become root-owned
   on the host and the next `rm -rf results` (README step 1) fails for the user.
2. Docker gets no `-w` unless `working_dir` is set, so `charge.log` (`workflow.yaml:130`) is
   written in the image's WORKDIR and lost after `--rm`; the tail still prints.
Not verified (no pull): that `openfe` is on `PATH` under `apptainer exec` for the
`-apptainer` image (exec skips the runscript).

**Fix.** Add `user: "1000:1000"` (your uid:gid) to the Docker example, and write the charge
log next to the output (`> ${charged}.log`) so it lands on a mounted path. Note the apptainer PATH as untested in Open Questions.

### m4 (minor) `workflow.yaml:30-31`: 24 h per leg is plausible but unproven, and without M1 a timeout is unrecoverable

**Problem.** One leg is 3 repeats x 11 replicas x 6 ns = 198 ns of hybrid-topology sampling,
run sequentially by quickrun. On a recent data-centre GPU this fits in 24 h for the ~37k-atom
complex; on older GPUs it may not. Combined with M1 a timeout is a hard stop.

**Fix.** After M1, mention in the README that a timed-out leg resumes on the next
`horus run`, and suggest `time_limit` be set to the site maximum.

### m5 (minor) `scripts/plan.py:63-69`: `alchemicalNetwork.json` from the CLI is not written

**Problem.** `plan-rbfe-network` also writes `<output_dir>/alchemicalNetwork.json` (via
`plan_alchemical_network_output`), which other openfe tools (`setup-task-campaign`,
`view-ligand-network` users) expect. `plan.py` writes only the transformations and the
graphml. Transformation file naming (`t.name or t.key`) matches upstream exactly.

**Fix.** Optional: `network.to_json(graphml.parent / "alchemicalNetwork.json")`, or note the
omission in Implementation Notes.

### m6 (minor) `params/profile.txt` is not gitignored

**Problem.** After the first run, `params/profile.txt` sits in the workflow folder and shows
up as untracked (`.gitignore` covers `horus_workflow_results/` but not `params/`). A
contributor could commit it, and a committed `profile.txt` overrides the YAML `value:` for
everyone.

**Fix.** Add `params/` to the workflow (or repo) `.gitignore`, as other workflows with root
parameter artifacts need too.

### m7 (minor) `scripts/select_ligands.py:13-21`: a last record without `$$$$` is dropped silently

**Problem.** `records()` only emits a record when it sees `$$$$`; a final record without the
terminator is discarded, and in `full` the output silently has one ligand fewer. The pinned
upstream file is well-formed (10 records, trailing `$$$$`), so this only bites the "your own
series" path.

**Fix.** After the loop, `if "".join(buf).strip(): out.append("".join(buf) + "$$$$\n")`, or
fail loudly. `report.py:sdf_records` is a second, different splitter (substring split, keeps
the unterminated record), so the two scripts can disagree on the same file; use the same
line-based splitter in both.

### m8 (minor) `scripts/report.py:73-75`: `strip("\n")` eats an empty molfile title line

**Problem.** A record whose name line is empty loses it, the header shifts up one line, Mol*
fails to parse that ligand and the label shows the program line ("  RDKit  3D"). The TYK2
records all have names, so only custom series are affected.

**Fix.** Split on `$$$$` lines as `select_ligands.records()` does and drop only the newline
that follows the separator.

### m9 (minor) `workflow.yaml:22-29`: `_gpu` hard-codes `cpus_per_task: 4` and `gres: gpu:1`

**Problem.** In `horus_slurm` explicit target values override the task `resources`, so the job
gets 4 CPUs while `OPENMM_CPU_THREADS=${task.resources.cpus}` says 2, and later edits to
`quickrun.resources` have no effect on the sbatch request. W-39's `_gpu` leaves both out.

**Fix.** Drop both lines; `resources: {cpus: 2, gpus: 1}` already derives
`--cpus-per-task=2 --gres=gpu:1`.

## Checks that passed

### Upstream fidelity (focus a)

`plan.py` was diffed against `openfecli/commands/plan_rbfe_network.py` in the openfe 1.13.0
conda env:
- Mapper, scorer, network planner, solvent come from `YAML_OPTIONS.get(None)`, the same call
  the CLI makes with no `-s`: `KartografAtomMapper`, `default_lomap_score`,
  `generate_minimal_spanning_network`, `SolventComponent(O, Na+, Cl-)` at 0.15 M.
- Protocol: `RelativeHybridTopologyProtocol.default_settings()` with nothing changed in full.
  Installed defaults: `protocol_repeats=3` (the CLI default of `--n-protocol-repeats` is also
  3), `compute_platform='cuda'`, 11 windows / 11 replicas, 1 ns eq / 5 ns prod,
  `solvent_padding=1.5 nm`, tip3p, dodecahedron.
- Charges: `openfe charge-molecules` and `plan-rbfe-network` both call
  `bulk_assign_partial_charges` with the `YAML_OPTIONS` defaults (am1bcc, ambertools,
  `overwrite=False`), so charging once up front gives the same molecules the CLI would plan
  with. `plan.py` refuses uncharged ligands, so nothing is recharged.
- Loaders: `MOL_DIR.get` / `PROTEIN.get`, the CLI's own getters. Cofactors empty, as in the
  tutorial.
- CLI flags used (`charge-molecules -M -o -n`, `quickrun -o -d`, `gather --report ddg|raw|dg -o`)
  all match `--help` of the installed 1.13.0.
- No upstream code copied wholesale; `plan.py` re-implements the ~20-line orchestration
  through the public API. Licenses verified via the GitHub API: openfe MIT,
  ExampleNotebooks MIT. Pinned commit and both tutorial links return 200.

### Leg naming and pairing (focus b)

Transformation JSONs are `rbfe_<A>_{complex,solvent}_<B>_{complex,solvent}.json`, identical
to the CLI. Each clone writes `${legs}/<stem>.json` into its own slot; `openfe gather` pairs
legs by the result content, not file names. The smoke run's `ddg.tsv` has both edges with
complex+solvent paired, and `raw.tsv` has all 4 legs.

### Map completeness (focus c)

A failed leg is not treated as complete: quickrun writes its result JSON (estimate `None`)
before exiting non-zero, but `HorusTask` writes the manifest only after `_execute` returns, and
`is_complete` requires the manifest, so the clone re-runs. With `on_item_failure: fail` gather
never sees the failed JSON. Work dirs stay under `legs/<slot>/work`; gather walks them but
ignores non-result JSON (confirmed by the smoke run). Gaps are M1 and M2.

### GPU path (focus d)

The env has `libOpenMMCUDA.so` (plus OpenCL/HIP) from conda-forge openmm 8.4.0 and
`cuda-version 13.4`; on this GPU-less host OpenMM lists only Reference and CPU, as expected.
Full transformations keep `compute_platform='cuda'`; smoke sets `'cpu'`. The README's note
about adding `cuda-version=12` for older drivers is correct. `_gpu` anchor: every field
(`inner`, `partition`, `account`, `gres`, `cpus_per_task`, `time_limit`) exists in
`horus_slurm` 0.5.1; empty `partition`/`account` are skipped (`if self.partition:`), explicit
`gres`/`cpus_per_task` win over task `resources`. The swap is `target: *gpu` plus filling
partition/account. `environment_dir: ../../.horus_conda_env` resolves to the same env for map
clones (`horus_workflow_results/quickrun[N]/<run>`).

### Horus conformance

- `uv run horus sanitize workflow.yaml -o <tmp> -y` reports "No root inputs to promote." and
  writes nothing, i.e. no diff.
- All 15 edges present; every task input has an incoming edge; the `profile` root artifact feeds
  `select_ligands`, `plan_network`, `gather`.
- Fields checked against horus-runtime v0.6.7 (`horus_map` `over{input_id,as}`,
  `max_concurrency`, `resources{cpus,gpus}`, `python_script{script,args,python}`,
  `orchestrator_target{working_directory}`) and horus-environments 0.1.4
  (`conda`, `environment_file`, `environment_dir`).

### Report (focus f)

`report.html` embeds the protein PDB and each ligand SDF record as JSON in a
`<script type=application/json>` block with `</` escaped; ligands load one structure each
(Mol* reads only the first SDF record). `molstar@5` resolves to 5.13.1 on jsdelivr, and its
`Viewer.loadStructureFromData(data, format, {dataLabel})` signature matches the call. Same
float-major URL as the w06 pattern; pinning an exact version (e.g. `molstar@5.13.1`) would
make old reports reproducible, a nit shared with w06 and not counted above. Smoke report: 424 KB, 3 ligands embedded.

### Selftests and smoke

- `python3 scripts/select_ligands.py --selftest`: ok
- `python3 scripts/report.py --selftest`: ok
- `scripts/plan.py --selftest` in the openfe env: ok
- Smoke not re-run here; the author's run in the w01 worktree log shows 885.6 s end to end
  (quickrun map 785.5 s) and an immediate second run that skipped all 7 tasks. That is under
  the plan's 45 min target and matches the README's 15 min.

### README

Quick start (`uv sync`, `uv run horus run workflow.yaml --no-tui`) matches the layout and the
measured run; the prerequisites (micromamba on PATH) are stated. Runtime and resource
numbers match the logs. Leg count for full (10 ligands, 9 edges, 18 legs) matches the 10
records in the pinned SDF.
