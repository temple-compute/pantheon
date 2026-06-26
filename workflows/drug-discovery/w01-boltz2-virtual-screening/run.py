#!/usr/bin/env python3
"""
W-01 driver — Boltz-2 virtual screening on the Horus runtime.

Builds and runs a 3-task workflow from ``config.yaml``:

    prep    (local)            target.fasta + ligands.smi -> boltz_inputs.tar.gz
      |  LocalToSSH transfer (automatic)
    predict (ssh GPU box)      boltz predict in a container -> predictions.tar.gz
      |  SSHToLocal transfer (automatic)
    rank    (local)            predictions.tar.gz -> top_hits.csv

The runtime has no workflow CLI yet, so this script *is* the entry point.
Switching the GPU stage between docker / singularity / baremetal is the
``engine`` knob; moving it between an SSH box and the local machine is the
``predict_target`` knob. Nothing else changes.

Usage:
    python run.py [config.yaml]      # defaults to ./config.yaml
"""

import asyncio
import shlex
import sys
from pathlib import Path

import yaml
from horus_builtin.artifact.file import FileArtifact
from horus_builtin.executor.shell import ShellExecutor
from horus_builtin.runtime.command import CommandRuntime
from horus_builtin.runtime.python_script import PythonScriptRuntime
from horus_builtin.target.local import LocalTarget
from horus_builtin.task.horus_task import HorusTask
from horus_builtin.workflow.horus_workflow import HorusWorkflow
from horus_runtime.context import HorusContext
from horus_runtime.core.target.base import BaseTarget
from horus_runtime.core.workflow.edge import WorkflowEdge

HERE = Path(__file__).parent
SCRIPTS = HERE / "scripts"


def predict_command(engine: str, image: str, boltz_args: str) -> str:
    """Build the GPU-stage shell command for the chosen container engine.

    The command is target-agnostic: ``${boltz_inputs}`` / ``${predictions}``
    resolve to the right on-target paths whether the task runs locally or over
    SSH. Steps are ``&&``-chained so any failure aborts with a non-zero code.
    """
    inner = {
        "docker": (
            f'docker run --rm --gpus all -v "$PWD":/work -w /work {image} '
            f"boltz predict inputs --out_dir out {boltz_args}"
        ),
        "singularity": (
            f"singularity exec --nv {image} "
            f"boltz predict inputs --out_dir out {boltz_args}"
        ),
        "baremetal": f"boltz predict inputs --out_dir out {boltz_args}",
    }
    if engine not in inner:
        raise ValueError(
            f"Unknown engine {engine!r}; use docker|singularity|baremetal"
        )
    return (
        "tar xzf ${boltz_inputs} -C . && "
        f"{inner[engine]} && "
        "tar czf ${predictions} -C out ."
    )


def build_ssh_target(cfg: dict, working_directory: str) -> BaseTarget:
    """Construct an SSHTarget from the ``ssh:`` config block.

    Imported lazily so a local-only run (``predict_target: local``) does not
    require the ``horus-ssh`` plugin to be installed.
    """
    from horus_ssh.target.ssh_target import SSHTarget

    keys = cfg.get("client_keys")
    return SSHTarget(
        host=cfg["host"],
        port=cfg.get("port", 22),
        username=cfg["username"],
        password=cfg.get("password"),
        client_keys=[str(Path(k).expanduser()) for k in keys] if keys else None,
        working_directory=working_directory,
        verify_host_key=cfg.get("verify_host_key", True),
    )


def build_workflow(config: dict) -> HorusWorkflow:
    """Assemble the 3-task workflow from a parsed config dict."""
    out_dir = Path(config["out_dir"]).expanduser().resolve()
    fasta = Path(config["inputs"]["fasta"]).expanduser().resolve()
    ligands = Path(config["inputs"]["ligands"]).expanduser().resolve()

    local = LocalTarget(working_directory=str(out_dir))

    # GPU stage runs on SSH by default; flip to "local" for a no-SSH smoke test.
    if config.get("predict_target", "ssh") == "local":
        predict_target: BaseTarget = LocalTarget(working_directory=str(out_dir))
    else:
        predict_target = build_ssh_target(
            config["ssh"], config["ssh"]["working_directory"]
        )

    # Cross-stage artifacts are single files (SSH transfer is file-based).
    boltz_inputs = FileArtifact(id="boltz_inputs", path=out_dir / "boltz_inputs.tar.gz")
    predictions = FileArtifact(id="predictions", path=out_dir / "predictions.tar.gz")
    top_hits = FileArtifact(id="top_hits", path=out_dir / "top_hits.csv")

    prep = HorusTask(
        id="prep",
        name="Build Boltz-2 inputs",
        target=local,
        executor=ShellExecutor(),
        runtime=PythonScriptRuntime(
            python=sys.executable,
            script=SCRIPTS / "prep.py",
            args=(
                f"--fasta {shlex.quote(str(fasta))} "
                f"--ligands {shlex.quote(str(ligands))} "
                "--out ${boltz_inputs}"
            ),
        ),
        outputs=[boltz_inputs],
    )

    predict = HorusTask(
        id="predict",
        name="Boltz-2 structure + affinity",
        target=predict_target,
        executor=ShellExecutor(),
        runtime=CommandRuntime(
            command=predict_command(
                config.get("engine", "docker"),
                config.get("image", "boltz2:latest"),
                config.get("boltz_args", "--use_msa_server"),
            ),
        ),
        inputs=[boltz_inputs],
        outputs=[predictions],
    )

    rank = HorusTask(
        id="rank",
        name="Rank hits",
        target=local,
        executor=ShellExecutor(),
        runtime=PythonScriptRuntime(
            python=sys.executable,
            script=SCRIPTS / "rank.py",
            args="--predictions ${predictions} --out ${top_hits}",
        ),
        inputs=[predictions],
        outputs=[top_hits],
    )

    # Explicit DAG edges: the runtime resolves both execution order and the
    # transfer source for each input from these (prep -> predict -> rank).
    edges = [
        WorkflowEdge(
            source="prep",
            source_output="boltz_inputs",
            target="predict",
            target_input="boltz_inputs",
        ),
        WorkflowEdge(
            source="predict",
            source_output="predictions",
            target="rank",
            target_input="predictions",
        ),
    ]

    return HorusWorkflow(
        name="Boltz2 Virtual Screening",
        tasks=[prep, predict, rank],
        edges=edges,
        orchestrator_target=LocalTarget(),
    )


async def _run(config: dict) -> None:
    HorusContext.boot()
    workflow = build_workflow(config)
    await workflow.run(trigger_id="prep")
    out_dir = Path(config["out_dir"]).expanduser().resolve()
    top = out_dir / "top_hits.csv"
    assert top.exists(), f"FAIL: {top} not produced"
    print(f"\n[w01] Done. Ranked hits: {top}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config_path = Path(argv[0]) if argv else HERE / "config.yaml"
    if not config_path.exists():
        sys.exit(
            f"Config not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )
    config = yaml.safe_load(config_path.read_text())
    asyncio.run(_run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
