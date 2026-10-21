# W-41 · Execution Path Coverage Harness

The same CPU-and-memory burn run once through every way horus-runtime can execute work, chained so each path's usage can be measured on its own.

![Domain: Engine Showcases](https://img.shields.io/badge/domain-engine--showcases-orange)

## Overview

An acceptance harness for per-task resource measurement. horus-runtime executes work in structurally different ways, and a monitor that measures one does not necessarily measure the others. Each task runs the same workload (touch ~300 MiB, burn ~4 s of CPU) through one execution path; all but `docker_container` append their label to a `chain` in a stamp JSON. `workflow.yaml` has 4 tasks. `run.py` adds a fifth, `python_function`, which cannot be expressed in YAML because it takes a live callable. `workflow.docker.yaml` holds the `docker_container` task.

## Pipeline

Tasks run one at a time so in-process tasks never share a process concurrently.

```
shell_command        shell + command                 subprocess on the target
shell_python_script  shell + python_script           subprocess, script shipped to target
uv_environment       uv_python_environment           subprocess inside a uv venv
python_exec_string   python + python                 in-process exec() of a code string
python_function      python_function (run.py only)   in-process direct call
docker_container     docker + command (workflow.docker.yaml)   container under the Docker daemon
```

## Inputs / Outputs

- Inputs: none. Each task except the first reads the previous task's stamp.
- `results/<task_id>.json`: `label`, `python`, `pid`, `allocated_mb`, `cpu_iterations`, `chain`; the script and `python_function` stamps also carry `peak_rss_mb`, and the script stamps `elapsed_s`.
- `uv_environment` must not set `runtime.python`; its stamp's `python` is the venv interpreter, not the system one.
- The in-process tasks share the orchestrator pid, so `python_exec_string` and `python_function` stamps carry the same `pid`.
- `docker_container` declares no outputs and writes to stdout only.

## Parameters

| id | Default | Meaning |
|---|---|---|
| `alloc_mb` | 300 | MiB each task allocates and touches (4-4096) |
| `burn_seconds` | 4 | Seconds each task spins one core (1-60) |

`run.py`'s `python_function` task and `workflow.docker.yaml` keep fixed 300 MiB / 4 s values.
