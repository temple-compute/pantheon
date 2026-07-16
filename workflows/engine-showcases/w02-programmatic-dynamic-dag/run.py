#!/usr/bin/env python3
"""
Programmatic dynamic-DAG showcase.

Run:
    uv run python run.py
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from horus_builtin.artifact.json import JSONArtifact
from horus_builtin.executor.python_fn import PythonFunctionExecutor
from horus_builtin.runtime.python import PythonFunctionRuntime
from horus_builtin.target.local import LocalTarget
from horus_builtin.task.function import FunctionTask
from horus_builtin.tui import render_workflow
from horus_builtin.workflow.horus_workflow import HorusWorkflow
from horus_runtime.context import HorusContext
from horus_runtime.core.workflow.edge import WorkflowEdge
from horus_runtime.logging import horus_logger

HERE = Path(__file__).parent
DATASET = HERE / "examples" / "dataset.json"
RESULTS = HERE / "results"

wf = HorusWorkflow(name="programmatic dynamic dag")


def _make_process_fn(group: str, records: list[dict[str, Any]]) -> Callable[..., None]:
    """Build the per-group task function as a closure over its matching records.

    A pure-Python workflow (never round-tripped through YAML) is free to use a
    closure here; the declarative `map:` template (see W-06) instead requires
    a *registered*, YAML-serializable function since it must survive
    `to_yaml`/`from_yaml`.
    """
    values = [r["n"] for r in records if r["group"] == group]

    def process(result: JSONArtifact) -> None:
        """Summarize this group's values into its own result artifact."""
        random_time = random.randint(0, 5)
        time.sleep(random_time)
        result.write(
            {"group": group, "count": len(values), "sum": sum(values), "values": values}
        )

    return process


def combine(combined: JSONArtifact, **kwargs: JSONArtifact) -> None:
    """Fan-in: sum every generated `process_<group>` task's result.

    The inputs are named `in_<group>` and injected via `**kwargs` because the
    set of groups — and therefore the set of parameter names — is only known
    once `plan` has read the data at runtime.
    """
    per_group: dict[str, dict[str, int]] = {}
    total_count = 0
    total_sum = 0
    for key, artifact in sorted(kwargs.items()):
        if not key.startswith("in_"):
            continue
        data = artifact.read()
        per_group[key[len("in_") :]] = {"count": data["count"], "sum": data["sum"]}
        total_count += data["count"]
        total_sum += data["sum"]
    combined.write(
        {"total_count": total_count, "total_sum": total_sum, "per_group": per_group}
    )


@FunctionTask.task(
    wf,
    id="plan",
    inputs=[JSONArtifact(id="dataset", path=DATASET)],
    skip_if_complete=False,
)
async def plan(dataset: JSONArtifact) -> None:
    """Read the dataset and expand the DAG: one process_<group> task per
    distinct group, plus a combine task fanning them all back in."""

    await asyncio.sleep(3)

    records = dataset.read()
    groups = sorted({r["group"] for r in records})
    horus_logger.log.info(f"plan: found {len(groups)} group(s): {groups}")

    workflow = HorusContext.get_context().workflow
    assert workflow is not None, "plan must run inside a live HorusContext"

    # One process_<group> task per group, added one at a time.
    for group in groups:
        process_task = FunctionTask(
            id=f"process_{group}",
            name=f"process_{group}",
            runtime=PythonFunctionRuntime(func=_make_process_fn(group, records)),
            executor=PythonFunctionExecutor(),
            outputs=[JSONArtifact(id="result", path=RESULTS / f"{group}.json")],
            target=LocalTarget(),
            skip_if_complete=False,
        )
        # No edge needed: created during plan's own execution,
        # so it can only run after plan completes.
        workflow.add_task(process_task)

        await asyncio.sleep(2)

    # One combine task, added together with all of its fan-in edges
    combine_task = FunctionTask(
        id="combine",
        name="combine",
        runtime=PythonFunctionRuntime(func=combine),
        executor=PythonFunctionExecutor(),
        inputs=[JSONArtifact(id=f"in_{g}", path=RESULTS / f"{g}.json") for g in groups],
        outputs=[JSONArtifact(id="combined", path=RESULTS / "combined.json")],
        target=LocalTarget(),
        skip_if_complete=False,
    )
    workflow.expand(
        tasks=[combine_task],
        edges=[
            WorkflowEdge(
                source=f"process_{g}",
                source_output="result",
                target="combine",
                target_input=f"in_{g}",
            )
            for g in groups
        ],
    )


def main() -> None:
    ctx = HorusContext.boot()
    try:
        render_workflow(wf, trigger_id="plan")
        # headless alternative:
        # import asyncio; asyncio.run(wf.run(trigger_id="plan"))
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    main()
