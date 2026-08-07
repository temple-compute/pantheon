# W-28 · Execution Path Coverage Harness

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

An acceptance harness for **per-task resource measurement**. horus-runtime can
execute a task in several structurally different ways — a subprocess on the
target, a subprocess inside a provisioned virtualenv, a container under a
daemon, or straight inside the orchestrator's own process — and an observer
that measures one of those does not automatically measure the others. Worse,
when it doesn't, nothing fails: the task succeeds and the measurement is
simply absent or zero.

This workflow exercises **every one of those paths**, in one DAG, with an
identical workload in each: touch ~300 MiB of pages and burn ~4s of CPU. So
after a run there is exactly one question per task — did the monitor see
~300 MB and ~100% CPU for ~4s, or not? Anything else is a gap.

Every task also carries an intentionally oversized advisory `resources:` block
(4 CPUs, 8 GB for a 1-core, 0.3 GB job), so right-sizing has something to
recover.

## Pipeline

Tasks run one at a time on purpose: two in-process tasks running concurrently
would land in the same process and make any in-process attribution ambiguous.

```
shell_command                       ──► results/shell_command.json
   │  shell executor + command runtime         (subprocess)
shell_python_script                 ──► results/shell_python_script.json
   │  shell executor + python_script runtime   (subprocess, script shipped to target)
uv_environment                      ──► results/uv_environment.json
   │  uv_python_environment executor           (subprocess inside a uv-built venv)
python_exec_string                  ──► results/python_exec_string.json
   │  python executor + python runtime         (IN-PROCESS, exec() of a code string)
python_function                     ──► results/python_function.json
   │  python_function executor                 (IN-PROCESS, direct call — run.py only)

workflow.docker.yaml (separate file, needs a Docker daemon)
docker_container                    ──► stdout only
   │  docker executor + command runtime        (CONTAINER, under the docker daemon)
```

Each task writes a stamp JSON recording `sys.executable`, `pid`, allocated
MiB, CPU iterations and peak RSS, and appends its own label to the `chain`
list it reads from the previous stamp — so `results/python_function.json`
lists all five paths and proves the whole DAG ran.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cd workflows/engine-showcases/w05-execution-path-coverage
uv sync

# Four of the five paths (everything expressible in YAML):
uv run horus run workflow.yaml

# All five, including the in-orchestrator python_function path:
uv run python run.py

# The container path (needs a running Docker daemon):
uv sync --extra docker
uv run horus run workflow.docker.yaml
```

Outputs land in `horus_workflow_results/results/`.

### Why `run.py` exists

`PythonFunctionRuntime` takes a live Python callable (`func`), so the
`python_function` executor **cannot be expressed in YAML at all** — a string
there fails validation with `Input should be callable`. `run.py` loads
`workflow.yaml`, appends that one task plus its edge with `workflow.expand()`,
and runs the combined DAG. `workflow.yaml` on its own stays a valid,
`horus run`-able, sanitize-clean workflow.

## Execution paths and what they map to

| Task | Executor | Runtime | Mechanism | `resource_scope()` |
|---|---|---|---|---|
| `shell_command` | `shell` | `command` | subprocess on the target (raw command string) | `ProcessTreeScope` |
| `shell_python_script` | `shell` | `python_script` | subprocess; script uploaded to the task working dir | `ProcessTreeScope` |
| `uv_environment` | `uv_python_environment` | `python_script` | subprocess inside a uv-provisioned venv | `ProcessTreeScope` |
| `python_exec_string` | `python` | `python` | **in-process**: `exec()` on the orchestrator's event loop | `InProcessScope` |
| `python_function` | `python_function` | `python_function` | **in-process**: the callable is invoked directly | `InProcessScope` |
| `docker_container` | `docker` | `command` | **container**: workload lives under the Docker daemon, in a different process group from the `docker run` client the runtime spawned | inherits the default `ProcessTreeScope` (of the *client*) |

Two details worth knowing, both of which have bitten someone already:

- The `uv_environment` task deliberately does **not** set `runtime.python`.
  The environment executor activates the venv and then runs the runtime's
  interpreter, so leaving the default (`python`) is what routes the script
  into the venv; pinning `python3` would silently run against the system
  interpreter and the task would still pass. Check `"python"` in
  `results/uv_environment.json` — it must point inside
  `horus_workflow_results/uv_environment/.horus_python_environment/`.
- The in-process tasks share the orchestrator's pid. Compare `pid` across the
  stamps: `python_exec_string` and `python_function` are equal to each other
  and different from every subprocess task.

## Acceptance table — fill this in after a run

Run the workflow with your resource monitor enabled and record what it
reported per task. Every row should be ~300 MB / ~100% CPU / ~4s; a row that
isn't is a path the monitor doesn't cover.

| Task | Samples produced? | Peak RAM reported | CPU% reported | Wall (s) | Matches the ~300 MB / ~100% / ~4s workload? |
|---|---|---|---|---|---|
| `shell_command` | | | | | |
| `shell_python_script` | | | | | |
| `uv_environment` | | | | | |
| `python_exec_string` | | | | | |
| `python_function` | | | | | |
| `docker_container` | | | | | |

Reference run (macOS 15, Apple silicon, `horus-resource-monitor` as of this
commit) — the point of the harness in one table:

| Task | Reported RAM | Reported CPU% | Wall (s) | Verdict |
|---|---|---|---|---|
| `shell_command` | 318.2 MB | 99 | 4.08 | measured |
| `shell_python_script` | 318.8 MB | 99 | 4.04 | measured |
| `uv_environment` | 319.1 MB | 97 | 4.17 | measured |
| `python_exec_string` | 0.0 MB | 0 | 4.02 | **nothing measured** |
| `python_function` | 0.0 MB | 0 | 4.07 | **nothing measured** |
| `docker_container` | 27.5 MB | 0 | 6.11 | **wrong process measured** (the `docker run` client, not the 300 MB container) |

The pattern is not a coincidence: that monitor instruments the *target
command*, so it covers exactly the executors that issue one. The two
in-process executors never call `target.run_command`, and the docker executor
calls it for a thin client whose real work is reparented under the daemon.

## Inputs / Outputs

**Input** — none. The first task is self-contained; every later task's input
is the previous task's stamp.

**Outputs** — `results/<task_id>.json`, one per task:

```json
{
  "label": "uv_environment",
  "python": ".../horus_workflow_results/uv_environment/.horus_python_environment/bin/python",
  "pid": 94404,
  "allocated_mb": 300,
  "cpu_iterations": 10690999,
  "elapsed_s": 4.03,
  "peak_rss_mb": 319.1,
  "chain": ["shell_command", "shell_python_script", "uv_environment"]
}
```

## Parameterization

- `--mb` / `--seconds` in `scripts/burn.py`'s invocations (`workflow.yaml`
  `args:`), and the equivalent literals in the two inline snippets
  (`shell_command`'s `command:` and `python_exec_string`'s `code:`). Defaults
  are 300 MiB / 4s per task — big and long enough to be unmistakable in a
  sampling monitor, small and short enough that the whole harness runs in
  ~20s.
- `resources:` blocks — advisory only; nothing enforces them here. They exist
  so a run has a request to compare measured usage against.

## Notes

- Observed wall time: ~4.1s per task, ~16s for `workflow.yaml`, ~20s for
  `run.py`, ~6s for the docker task (plus a one-off image pull).
- The uv venv is built under `horus_workflow_results/uv_environment/` and is
  reused on later runs; delete `horus_workflow_results/` for a cold run.
- `workflow.docker.yaml`'s task declares no outputs: `DockerExecutor` mounts
  nothing by default, so a container cannot write into the task working
  directory unless you add `volumes:` yourself.
