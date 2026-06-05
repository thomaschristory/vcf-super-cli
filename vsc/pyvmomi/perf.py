"""``vsc vsphere perf`` — performance counters via the pyVmomi PerformanceManager.

The vAPI/REST surface has no performance API, so this reads counters over SOAP.
Metrics are named ``group.name`` (e.g. ``cpu.usage``) or ``group.name.rollup``
(e.g. ``cpu.usage.average``); the short form resolves to the first rollup seen.
"""

from __future__ import annotations

from typing import Any

import typer
from pyVmomi import vim

from vsc.connect.vmomi import vmomi_jsonable
from vsc.gen.complete import output_format_completer
from vsc.output.render import OutputFormat
from vsc.pyvmomi.runner import run_read

perf_app = typer.Typer(no_args_is_help=True, help="Performance metrics (pyVmomi fallback).")

# Sensible defaults when the caller names no metric explicitly.
_DEFAULT_METRICS = ["cpu.usage", "mem.usage"]


def counter_index(perf_counters: list[Any]) -> dict[str, int]:
    """Map ``group.name`` and ``group.name.rollup`` to their counter id."""
    index: dict[str, int] = {}
    for counter in perf_counters:
        full = f"{counter.groupInfo.key}.{counter.nameInfo.key}.{counter.rollupType}"
        short = f"{counter.groupInfo.key}.{counter.nameInfo.key}"
        index[full] = counter.key
        index.setdefault(short, counter.key)  # first rollup wins for the short alias
    return index


def query_perf(
    perf_manager: Any, entity: Any, metrics: list[str], *, max_samples: int
) -> list[dict[str, Any]]:
    """Query ``metrics`` for ``entity`` and shape the result as JSON-able dicts."""
    index = counter_index(perf_manager.perfCounter)
    name_by_id: dict[int, str] = {}
    metric_ids: list[Any] = []
    for metric in metrics:
        counter_id = index.get(metric)
        if counter_id is None:
            raise ValueError(f"unknown metric {metric!r} (try `<group>.<name>`, e.g. cpu.usage)")
        name_by_id[counter_id] = metric
        metric_ids.append(vim.PerfMetricId(counterId=counter_id, instance="*"))

    spec = vim.PerfQuerySpec(entity=entity, metricId=metric_ids, maxSample=max_samples)
    results = perf_manager.QueryPerf(querySpec=[spec]) or []

    out: list[dict[str, Any]] = []
    for entity_metric in results:
        samples = [
            {"timestamp": info.timestamp.isoformat(), "interval": info.interval}
            for info in (entity_metric.sampleInfo or [])
        ]
        series = [
            {
                "metric": name_by_id.get(s.id.counterId, s.id.counterId),
                "instance": s.id.instance,
                "values": list(s.value),
            }
            for s in (entity_metric.value or [])
        ]
        out.append(
            {"entity": vmomi_jsonable(entity_metric.entity), "samples": samples, "series": series}
        )
    return out


def _run_entity(moid: str, kind: str, metrics: list[str], max_samples: int, fmt: str) -> None:
    cls = vim.VirtualMachine if kind == "vm" else vim.HostSystem

    def build(si: Any) -> list[dict[str, Any]]:
        entity = cls(moid, si._stub)
        return query_perf(si.content.perfManager, entity, metrics, max_samples=max_samples)

    run_read(fmt, build)


_METRIC_HELP = "Metric as group.name[.rollup] (repeatable), e.g. cpu.usage."


@perf_app.command("vm")
def perf_vm(
    vm: str = typer.Argument(..., help="VM managed-object id, e.g. vm-101."),
    metric: list[str] = typer.Option(None, "--metric", help=_METRIC_HELP),
    max_samples: int = typer.Option(15, "--max-samples", help="Number of samples to return."),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """Performance counters for a virtual machine."""
    _run_entity(vm, "vm", metric or _DEFAULT_METRICS, max_samples, output.value)


@perf_app.command("host")
def perf_host(
    host: str = typer.Argument(..., help="Host managed-object id, e.g. host-12."),
    metric: list[str] = typer.Option(None, "--metric", help=_METRIC_HELP),
    max_samples: int = typer.Option(15, "--max-samples", help="Number of samples to return."),
    output: OutputFormat = typer.Option(
        OutputFormat.json,
        "--output",
        "-o",
        help="Output format.",
        autocompletion=output_format_completer(),
    ),
) -> None:
    """Performance counters for an ESXi host."""
    _run_entity(host, "host", metric or _DEFAULT_METRICS, max_samples, output.value)
