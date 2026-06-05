"""`vsc vsphere tasks list` (pyVmomi TaskManager) — helper + CLI."""

from __future__ import annotations

import json
from typing import Any

import pytest
import typer
from pyVmomi import vim
from typer.testing import CliRunner

from vsc.pyvmomi.tasks import recent_tasks, tasks_app

runner = CliRunner()


class _FakeTask:
    def __init__(self, info: Any) -> None:
        self.info = info


def _info(key: str, state: str, desc: str) -> vim.TaskInfo:
    return vim.TaskInfo(key=key, state=state, descriptionId=desc, entityName="web-1")


class _FakeTM:
    def __init__(self, tasks: list[Any]) -> None:
        self.recentTask = tasks


def _fake_si(tm: _FakeTM) -> Any:
    content = type("C", (), {"taskManager": tm})()
    return type("SI", (), {"content": content, "_stub": object()})()


def test_recent_tasks_shapes_info() -> None:
    tm = _FakeTM([_FakeTask(_info("task-1", "success", "VirtualMachine.powerOn"))])
    out = recent_tasks(tm)
    assert out[0]["state"] == "success"
    assert out[0]["descriptionId"] == "VirtualMachine.powerOn"


def test_recent_tasks_caps_to_most_recent() -> None:
    tm = _FakeTM([_FakeTask(_info(f"task-{i}", "success", "x")) for i in range(5)])
    out = recent_tasks(tm, max_count=2)
    assert [t["key"] for t in out] == ["task-3", "task-4"]  # most recent kept


def _app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(tasks_app, name="tasks")
    return app


def test_tasks_list_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    tm = _FakeTM([_FakeTask(_info("task-1", "running", "VirtualMachine.reconfigure"))])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(tm))
    result = runner.invoke(_app(), ["tasks", "list"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["state"] == "running"
