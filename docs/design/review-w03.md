# Review: W-39 OpenFF Protein-Ligand MD (`workflows/omsf/w03-openff-protein-ligand-md`)

Branch `chdominguez/omsf-w03-openff` at `f10f835`, reviewed against `feat/omsf-workflows` and
`docs/plans/omsf-workflows.md` sections 1, 3 (W-39) and 4. Read-only: no workflow code was changed.

Counts: 0 blocker, 4 major, 12 minor.

## What was verified

- `--selftest`: `analyze.py`, `parameterize.py`, `simulate.py` pass on host Python. `build_system.py`
  passes only with the env interpreter (see m5).
- `horus sanitize workflow.yaml -o /tmp/x.yaml -y` (horus-runtime 0.6.7 from tc-os, and 0.7.0 from
  `uv sync`): "No root inputs to promote", no output and no diff. Clean.
- YAML fields checked against the 0.6.7 / plugin sources: `conda_python_environment{conda,
  environment_file, environment_dir}` (horus_environments 0.1.4), `slurm{inner, partition, account,
  ntasks, cpus_per_task, gres, time_limit}` (horus_slurm 0.5.1), `choice{options[value,label], path,
  value}`, `horus_map.over{input_id, as}`, `resources{cpus,gpus,memory_gb}`, `python_script{script,
  args}`, `orchestrator_target.working_directory`. All exist. Note that models accept unknown keys
  silently (a `bogus_field` in `_gpu` still loads), so this was checked by reading the source, not by
  loading. All 7 edges are present and complete; every non-root input is fed.
- GPU swap: changing only `simulate.target` to `*gpu` loads as `SlurmTarget(gres=gpu:1)`. Empty
  `partition`/`account` are skipped by `_build_sbatch_script`, so an unedited anchor does not emit
  `--partition=`.
- Container note in the README is correct: `docker` and `singularity` executors declare
  `runtimes = (CommandRuntime,)`, so `python_script` tasks would have to become commands.
- Independent smoke run (copy of the branch in a scratch dir, `uv sync && uv run horus run
  workflow.yaml --no-tui`, `taskset -c 0-3`, author's env reused via symlink): succeeded in 9:45
  wall (fetch 0.6 s, build_system 248 s, parameterize 34 s, simulate 2 x ~290 s in parallel,
  analyze 2 s; peak RSS 0.85 GB). An immediate re-run skips all 5 tasks in 0.09 s.
- Env: OpenMM 8.6.1 ships `libOpenMMCUDA.so` / OpenCL plugins in the env solved on this CPU host;
  `getPluginLoadFailures()` shows CUDA fails only on `libcuda.so.1` (no driver here), so the CUDA
  claim holds. `cuda-version 13.4`, `cuda-nvrtc 13.4.92`, `pytorch 2.6.0 cpu`. `openff-2.3.0.offxml`
  uses `<NAGLCharges model_file="openff-gnn-am1bcc-1.0.0.pt">`, so no AmberTools is needed, as stated.
- Science vs the 0.19.0 notebook: same inputs, PDBFixer `addSolvent(padding=1 nm,
  ionicStrength=0.15 M)`, `Topology.from_pdb`, ligand appended from the SDF conformer, 1.5 A clash
  radius, box vectors carried over, `ForceField("openff-2.3.0.offxml",
  "ff14sb_off_impropers_0.0.4.offxml").create_interchange`, 300 K / 1 ps^-1 / 2 fs, NVT. PDBFixer
  does not translate the solute (receptor coordinates are unchanged after solvation), so the SDF pose
  stays in the pocket: 0 clashing waters, nearest protein heavy atom 1.89 A from the ligand, 24,239
  atoms, 7,466 waters, 45 ions, 63.7 A cubic box. Deviations are listed under m7.
- Outputs: `rmsd.csv` (10 frames per replica), `final_frame.pdb` (protein with ACE/NME caps plus
  38-atom ligand `UNK`, no solvent). `report.html` renders in headless Chromium: stat cards, table and
  the Mol* frame all load from the CDN. Only the 3D canvas could not be checked, because the sandbox
  has no WebGL ("WebGL does not seem to be available" comes from Mol* itself, so the script loaded).
- Download boundary: `curl -fL --retry 3 -o X.part && mv` matches the plan. `skip_if_complete` in
  0.6.7 requires all outputs plus a manifest that is written only after success, so a crashed clone
  or a half-written `.part` never counts as complete.
- License/credit: upstream is MIT, "Copyright (c) 2016-2019 Open Force Field Initiative". Credited
  with links to tag 0.19.0. The clash helper is reimplemented, not copied. All links resolve.

## Major

### M1. Switching `profile` is a silent no-op: everything is skipped and smoke results are reported as full
`workflow.yaml:33-45`, `README.md:70-82`. Problem: `ValueArtifact.materialize` writes
`params/profile.txt` only when it is missing. The task fingerprint hashes that file's bytes plus the
unrendered args string `--profile ${profile}`, so flipping the root value does not change any
fingerprint. Reproduced: smoke run, then `value: full`, then `horus run`, and all 5 tasks report
"Already complete". `${profile}` itself renders correctly (known-good rule); the problem is cache
invalidation only. The README covers this with "delete `horus_workflow_results/` except
`.horus_conda_env/`", but that is easy to miss when the profile is changed from the UI dropdown,
and it throws away the profile-independent fetch and build_system results (about 4-7 min).
Fix: document the minimal step, which is to delete `params/profile.txt` (the next run re-materializes
it from the new value, its digest changes, and only parameterize/simulate/analyze re-run. Verified:
fetch and build_system were skipped, parameterize wrote 3 slots and the 3 clones started. See M2),
and file a runtime issue (fingerprint the value, or re-materialize when the value differs from the
file). Long term this belongs in horus-runtime, not in each workflow.

### M2. Going from full to smoke leaves a stale `trajectories/2/`, and `analyze` mixes it into the report
`scripts/analyze.py:104`, `scripts/parameterize.py:22`. Problem: `parameterize` clears `replicas/`,
but nothing clears `trajectories/`. A map clone rewrites only its own `trajectories/<i>/`, and the
runtime does not delete outputs before a re-run. After a full run (3 replicas), a smoke run
re-creates slots 0 and 1, and `analyze` iterates every directory, so it reports replica 2 at 1 ns next
to two 5 ps replicas. Fix: have `analyze` read only the replicas present in the current slots. For
example, feed `replicas/` to `analyze` as a second input and iterate its names, or have `simulate`
write the profile into each output and have `analyze` assert they all match.

### M3. CUDA fallback only covers `getPlatformByName`; a CUDA plugin that loads but cannot create a context crashes
`scripts/simulate.py:17-23,43`. Problem: on a host with `libcuda` but an unusable GPU (driver older
than the CUDA 13.4 runtime, `CUDA_VISIBLE_DEVICES=""`, exclusive-process GPU taken by the other
clone), `getPlatformByName("CUDA")` succeeds and `app.Simulation(...)` then raises
`OpenMMException` outside the `try`. The clone fails and `on_item_failure: fail` fails the map. This
contradicts README "CUDA when OpenMM can load it, else CPU". Fix: create the `Simulation` inside the
selection, trying CUDA, then OpenCL, then CPU, and log the reason for each fallback.

### M4. On the GPU target a missing GPU silently falls back to 2-thread CPU and then times out
`scripts/simulate.py:23`, `workflow.yaml:30`. Problem: with `profile=full` on `*gpu`, any CUDA
failure (gres not granted, driver mismatch) runs 500,000 steps at about 3.5 ns/day, which is about
7 h. Slurm kills each clone at `04:00:00`, after burning 3 allocations, and the only hint is one log
line. Fix: fail fast when a GPU is expected, for example with a `--require-gpu` flag set in the
full-profile args, or by refusing CPU when `profile == "full"`.

## Minor

### m1. Driver guidance is likely too lax for OpenMM's runtime-compiled kernels
`README.md:84-89`. Problem: the env carries `cuda-nvrtc 13.4`. OpenMM JIT-compiles its kernels, and
code from a newer nvrtc can be rejected by an older driver (`CUDA_ERROR_UNSUPPORTED_PTX_VERSION`) even
inside the 13.x minor-version-compat range. "driver >= 580" may not be enough. (Plausible, not
reproduced: no GPU here.) Fix: tell users to pin `cuda-version` to at most the CUDA version that
`nvidia-smi` reports, rather than giving a fixed driver floor.

### m2. Clash filter can delete ions and leave a charged system
`scripts/build_system.py:18,26`. Problem: `n <= 3` matches Na+ and Cl- as well as water. Dropping
one ion leaves a net charge under PME, with no warning. This is latent for 5TBM (0 removed) but
reachable with other inputs. Fix: print what was removed (the notebook prints each removed
molecule's SMILES), and either keep ions or warn when the removed set has a net charge.

### m3. `_gpu` repeats `cpus_per_task`/`gres` that horus-slurm derives from `resources`
`workflow.yaml:27-29`. Problem: explicit anchor values win over `resources`, so raising
`simulate.resources.gpus` or `cpus` later has no effect on sbatch. Fix: drop both keys (the sbatch
lines are the same today) or add a comment that they override `resources`.

### m4. Replica slots duplicate 8.7 MB each, and every clone fingerprints all slots
`scripts/parameterize.py:20-28`. Problem: `system.xml` (6.6 MB) and `complex.pdb` (2.1 MB) are copied
into every slot, again into `parameterized/`, and `complex.pdb` again into each trajectory. Fix
(optional): slots hold only `seed`, and system/complex come in as one shared, non-iterated map input.

### m5. `build_system.py --selftest` needs numpy
`scripts/build_system.py:14`. Problem: the module-level `import numpy` breaks the selftest on host
Python (plan §4.1: "runs without the heavy deps where possible"). Fix: import numpy inside `build`
and `clashing`, or write the clash test in pure Python.

### m6. Undeclared side files in the shared results root
`scripts/parameterize.py:37`, `scripts/build_system.py:44`. Problem: `parameterized/` and
`system/receptor_solvated.pdb` are written outside declared outputs. They are not transferred on
non-local targets and no manifest tracks them. Fix: write them under the task's working dir or a
temp dir.

### m7. Undocumented science deviations from the notebook
`scripts/simulate.py:39`, `README.md:141-144`. Problem: the notebook uses `LangevinIntegrator`, the
port `LangevinMiddleIntegrator`. The notebook builds the simulation with
`interchange.to_openmm_simulation`, the port with `to_openmm_system` plus `to_pdb` positions (PDB
precision 0.001 A). The full profile (1 ns, frame every 10 ps) is "upstream-like" per the plan; the
notebook runs `runForClockTime(1 min)` with stride 1000 on CUDA. All of these are reasonable, but
only the clock-time change is documented. Fix: add one line each to Implementation Notes.

### m8. "fixed step count so runs are reproducible" overclaims
`README.md:143-144`. Problem: with fixed seeds, two smoke runs on the CPU platform gave different
RMSDs (replica 0, frame 0: 0.570 vs 0.588 A), because CPU summation order varies with threads.
Fix: say "fixed length and seeds" and drop "reproducible", or note that bitwise reproducibility
needs the Reference platform or deterministic forces.

### m9. Smoke length differs from the plan
`scripts/simulate.py:12`. Problem: plan §3 W-39 says "smoke: 5k steps", the code runs 2,500 (5 ps).
Fix: reconcile the plan or the code. 2,500 keeps the run inside the 15 min budget on a loaded host,
so updating the plan is the cheaper fix.

### m10. GPU time estimate is pessimistic
`README.md:26`. Problem: "~10-20 min each" for 1 ns of 24k atoms at 2 fs. A modern GPU runs this
size at several hundred ns/day, so a run takes a few minutes plus minimization. The 4 h
`time_limit` is fine as a cap. Fix: say "a few minutes on a modern GPU (estimate)", or leave it and
mark it as a conservative upper bound.

### m11. `analyze` crashes on any non-numeric directory in `trajectories/`
`scripts/analyze.py:104`. Problem: `key=lambda p: int(p.name)` raises `ValueError` for a stray dir.
Fix: filter `p.name.isdigit()`. This is subsumed by the M2 fix if `analyze` iterates the slot names.

### m12. Branch housekeeping and Quick start nits
Problem: the branch is not rebased on `feat/omsf-workflows`, so it lacks `4e05ebb` (gitignore for
materialized params) and `params/profile.txt` shows up untracked in the worktree. Quick start also
assumes the reader has already `cd`ed into the workflow directory. Separately, `pyproject.toml`
`>=` pins resolve to horus-runtime 0.7.0 / horus-slurm 0.5.1 under `uv sync`, not the 0.6.7 the plan
verified. The run worked on 0.7.0, but `horus sanitize` there logs `Failed to load plugin
horus_slurm.probe: No module named 'horus_resource_monitor'` (this is repo-wide, not specific to
W-39). Fix: rebase, and add `cd workflows/omsf/w03-openff-protein-ligand-md` to Quick start.

## Not checked

- The Slurm/GPU path was not run (no cluster), and there is no GPU here for the CUDA platform or
  the m1 driver question.
- The Mol* 3D canvas was not visually confirmed (no WebGL in headless Chromium).
- A full-profile run was not done.
