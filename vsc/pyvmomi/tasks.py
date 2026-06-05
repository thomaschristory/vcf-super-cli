"""``vsc vsphere tasks list`` — recent + running tasks via the pyVmomi TaskManager."""

from __future__ import annotations

from typing import Any

import typer

from vsc.connect.vmomi import vmomi_jsonable
from vsc.gen.complete import output_format_completer
from vsc.output.render import OutputFormat
from vsc.pyvmomi.runner import run_read

tasks_app = typer.Typer(no_args_is_help=True, help="Recent and running tasks (pyVmomi fallback).")


def recent_tasks(task_manager: Any, *, max_count: int | None = None) -> list[dict[str, Any]]:
    """Return the ``TaskInfo`` of recent tasks (most recent last), shaped as dicts."""
    infos = [task.info for task in (task_manager.recentTask or [])]
    if max_count is not None:
        infos = infos[-max_count:]  # recentTask is oldest-first; keep the newest
    return [vmomi_jsonable(info) for info in infos]


@tasks_app.command("list")
def tasks_list(
    max_count: int = typer.Option(100, "--max-count", help="Cap the number of tasks returned."),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """List recent and running tasks."""

    def build(si: Any) -> list[dict[str, Any]]:
        return recent_tasks(si.content.taskManager, max_count=max_count)

    run_read(output.value, build)
