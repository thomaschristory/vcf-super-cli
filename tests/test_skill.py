"""Bundled Skill export tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vsc.cli.app import app
from vsc.skill.export import export_path, skill_text

runner = CliRunner()


def test_skill_text_has_frontmatter_and_contract() -> None:
    text = skill_text()
    assert "name: vcf-super-cli" in text
    assert "vsc vsphere" in text and "vsc nsx" in text
    assert "Output is JSON by default" in text


def test_export_dry_run_does_not_write(tmp_path: Path) -> None:
    result = runner.invoke(app, ["skill", "export", str(tmp_path)])
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["dry_run"] is True
    assert not export_path(tmp_path).exists()


def test_export_apply_writes_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["skill", "export", str(tmp_path), "--apply"])
    assert result.exit_code == 0
    target = export_path(tmp_path)
    assert target.exists()
    assert target.read_text(encoding="utf-8") == skill_text()
    assert json.loads(result.stdout)["written"] == str(target)
