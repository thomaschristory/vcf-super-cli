"""`vsc skill` commands: export the bundled agent Skill."""

from __future__ import annotations

from pathlib import Path

import typer

from vsc.output.render import to_json
from vsc.skill.export import export_path, export_skill

skill_app = typer.Typer(no_args_is_help=True, help="The bundled agent Skill.")


@skill_app.command("export")
def export(
    directory: Path = typer.Argument(..., help="Directory to export the Skill into."),
    apply: bool = typer.Option(
        False, "--apply", help="Actually write the file (otherwise dry-run prints the path)."
    ),
) -> None:
    """Export the bundled SKILL.md to ``<directory>/vcf-super-cli/SKILL.md``."""
    target = export_path(directory)
    if not apply:
        print(to_json({"dry_run": True, "would_write": str(target)}))
        return
    written = export_skill(directory)
    print(to_json({"written": str(written)}))
