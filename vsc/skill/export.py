"""Read the bundled agent Skill and export it to a directory."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_SKILL_NAME = "vcf-super-cli"


def skill_text() -> str:
    """Return the bundled SKILL.md content."""
    return (files("vsc.skill") / "assets" / "SKILL.md").read_text(encoding="utf-8")


def export_path(dest_dir: Path) -> Path:
    """The file that :func:`export_skill` would write under ``dest_dir``."""
    return dest_dir / _SKILL_NAME / "SKILL.md"


def export_skill(dest_dir: Path) -> Path:
    """Write the bundled SKILL.md to ``dest_dir/vcf-super-cli/SKILL.md``."""
    target = export_path(dest_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(skill_text(), encoding="utf-8")
    return target
