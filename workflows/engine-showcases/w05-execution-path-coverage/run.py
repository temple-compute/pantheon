#!/usr/bin/env python3
"""Run the full execution-path coverage harness, including the in-orchestrator
`python_function` path that `workflow.yaml` cannot express.

`PythonFunctionRuntime` takes a live Python callable (`func`), so there is no
YAML spelling for it. This script loads `workflow.yaml`, appends the function
task and its edge, and runs the resulting DAG — every execution path in one
graph.

Run:
    uv run python run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from horus_builtin.artifact.file import FileArtifact
from horus_builtin.executor.python_fn import PythonFunctionExecutor
from horus_builtin.runtime.python import PythonFunctionRuntime
from horus_builtin.target.local import LocalTarget
from horus_builtin.task.function import FunctionTask
from horus_runtime.context import HorusContext
from horus_runtime.core.workflow.base import BaseWorkflow
from horus_runtime.core.workflow.edge import WorkflowEdge

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "scripts"))

from burn import burn, peak_rss_mb  # noqa: E402  (needs the path above)


def burn_in_process(prev: FileArtifact, stamp: FileArtifact) -> None:
    """Same workload as scripts/burn.py, called directly on the event loop.

    No subprocess exists for this task, so anything measured here is the
    orchestrator's own usage — shared with the runtime itself and with any
    other task in flight. That is exactly what makes this path the interesting
    one for a resource monitor.
    """
    nbytes, iterations = burn(mb=300, seconds=4.0)
    with open(prev.path, encoding="utf-8") as fh:
        chain = json.load(fh).get("chain", [])
    os.makedirs(os.path.dirname(stamp.path), exist_ok=True)
    with open(stamp.path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "label": "python_function",
                "python": sys.executable,
                "pid": os.getpid(),
                "allocated_mb": nbytes >> 20,
                "cpu_iterations": iterations,
                "peak_rss_mb": round(peak_rss_mb(), 1),
                "chain": [*chain, "python_function"],
            },
            fh,
            indent=2,
        )


def main() -> None:
    # Boot first: plugin kinds (`horus_workflow`, `uv_python_environment`, ...)
    # are registered at boot, so `from_yaml` can't resolve them before it.
    ctx = HorusContext.boot()
    try:
        run(BaseWorkflow.from_yaml(HERE / "workflow.yaml"))
    finally:
        ctx.shutdown()


def run(wf: BaseWorkflow) -> None:
    wf.expand(
        tasks=[
            FunctionTask(
                id="python_function",
                name="Python function executor",
                description=(
                    "In-process path — the function is called directly on the "
                    "orchestrator's event loop."
                ),
                runtime=PythonFunctionRuntime(func=burn_in_process),
                executor=PythonFunctionExecutor(),
                inputs=[
                    FileArtifact(
                        id="prev", path=Path("results/python_exec_string.json")
                    )
                ],
                outputs=[
                    FileArtifact(
                        id="stamp", path=Path("results/python_function.json")
                    )
                ],
                target=LocalTarget(),
                skip_if_complete=False,
            )
        ],
        edges=[
            WorkflowEdge(
                source="python_exec_string",
                source_output="stamp",
                target="python_function",
                target_input="prev",
            )
        ],
    )

    asyncio.run(wf.run(trigger_id=wf.tasks[0].id))
    # TUI alternative:
    # from horus_builtin.tui import render_workflow
    # render_workflow(wf, trigger_id=wf.tasks[0].id)


if __name__ == "__main__":
    main()
