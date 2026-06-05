"""`vsc vsphere perf` (pyVmomi PerformanceManager) — helpers, CLI, error mapping."""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import pytest
import typer
from pyVmomi import vim, vmodl
from typer.testing import CliRunner

from vsc.output.exit_codes import ExitCode
from vsc.pyvmomi.perf import counter_index, perf_app, query_perf

runner = CliRunner()


def _counter(key: int, group: str, name: str, rollup: str) -> vim.PerfCounterInfo:
    desc = lambda k: vim.ElementDescription(key=k, label=k, summary=k)  # noqa: E731
    return vim.PerfCounterInfo(
        key=key,
        groupInfo=desc(group),
        nameInfo=desc(name),
        unitInfo=desc("num"),
        rollupType=rollup,
        statsType="rate",
    )


def _entity_metric() -> vim.PerfEntityMetric:
    return vim.PerfEntityMetric(
        entity=vim.VirtualMachine("vm-1", None),
        sampleInfo=[
            vim.PerfSampleInfo(
                timestamp=_dt.datetime(2026, 6, 5, 12, 0, tzinfo=_dt.UTC), interval=20
            )
        ],
        value=[
            vim.PerfMetricIntSeries(id=vim.PerfMetricId(counterId=2, instance=""), value=[10, 20])
        ],
    )


class _FakePM:
    def __init__(self, counters: list[Any], results: Any) -> None:
        self.perfCounter = counters
        self._results = results

    def QueryPerf(self, querySpec: Any) -> Any:
        if isinstance(self._results, Exception):
            raise self._results
        return self._results


def _fake_si(pm: _FakePM) -> Any:
    content = type("C", (), {"perfManager": pm})()
    return type("SI", (), {"content": content, "_stub": object()})()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def test_counter_index_maps_full_and_short_names() -> None:
    idx = counter_index([_counter(2, "cpu", "usage", "average")])
    assert idx["cpu.usage.average"] == 2
    assert idx["cpu.usage"] == 2  # short alias


def test_query_perf_shapes_result() -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], [_entity_metric()])
    out = query_perf(pm, vim.VirtualMachine("vm-1", None), ["cpu.usage"], max_samples=5)
    assert out[0]["entity"] == {"type": "VirtualMachine", "value": "vm-1"}
    series = out[0]["series"][0]
    assert series["metric"] == "cpu.usage"
    assert series["values"] == [10, 20]
    assert out[0]["samples"][0]["interval"] == 20


def test_query_perf_rejects_unknown_metric() -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], [])
    with pytest.raises(ValueError, match="unknown metric"):
        query_perf(pm, vim.VirtualMachine("vm-1", None), ["bogus.metric"], max_samples=5)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _app() -> typer.Typer:
    app = typer.Typer()
    app.add_typer(perf_app, name="perf")
    return app


def test_perf_vm_cli_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], [_entity_metric()])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pm))
    result = runner.invoke(_app(), ["perf", "vm", "vm-1", "--metric", "cpu.usage"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert out[0]["series"][0]["metric"] == "cpu.usage"


def test_perf_host_cli_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], [_entity_metric()])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pm))
    result = runner.invoke(_app(), ["perf", "host", "host-12", "--metric", "cpu.usage"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)[0]["series"][0]["metric"] == "cpu.usage"


def test_perf_unknown_metric_is_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], [])
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pm))
    result = runner.invoke(_app(), ["perf", "vm", "vm-1", "--metric", "no.such"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert json.loads(result.stderr)["error"]["code"] == int(ExitCode.USAGE)


def test_perf_not_found_fault_maps_to_exit_4(monkeypatch: pytest.MonkeyPatch) -> None:
    fault = vmodl.fault.ManagedObjectNotFound(msg="no such vm")
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], fault)
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pm))
    result = runner.invoke(_app(), ["perf", "vm", "vm-404", "--metric", "cpu.usage"])
    assert result.exit_code == int(ExitCode.NOT_FOUND)
    assert json.loads(result.stderr)["error"]["kind"] == "ManagedObjectNotFound"


def test_perf_auth_fault_maps_to_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = _FakePM([_counter(2, "cpu", "usage", "average")], vim.fault.NoPermission(msg="denied"))
    monkeypatch.setattr("vsc.pyvmomi.runner.connect_vmomi", lambda: _fake_si(pm))
    result = runner.invoke(_app(), ["perf", "vm", "vm-1", "--metric", "cpu.usage"])
    assert result.exit_code == int(ExitCode.AUTH)
