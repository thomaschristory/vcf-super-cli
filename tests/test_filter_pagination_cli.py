"""Issue B: per-field filter flags + pagination, end-to-end through generated commands."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import typer
from typer.testing import CliRunner

from vsc.gen.builder import make_command
from vsc.gen.discover import discover_operations, nsx_services, vsphere_services
from vsc.gen.model import Operation

runner = CliRunner()


def _op(service_name: str, backend: str, verb: str) -> Operation:
    services = vsphere_services() if backend == "vsphere" else nsx_services()
    cls = next(c for c in services if c.__name__ == service_name)
    return next(o for o in discover_operations(cls, backend) if o.cli_verb == verb)


def _app(op: Operation, service_cls: type) -> typer.Typer:
    op2 = dataclasses.replace(op, service_cls=service_cls)
    app = typer.Typer()
    app.command(op2.cli_verb)(make_command(op2, lambda _b: object()))
    return app


# --------------------------------------------------------------------------- #
# Per-field filter flags
# --------------------------------------------------------------------------- #

_CAPTURED: dict[str, Any] = {}


def _fake_vm_list(rows: list[dict[str, Any]]) -> type:
    class FakeVM:
        def __init__(self, _cfg: object) -> None:
            pass

        def list(self, **kwargs: Any) -> list[dict[str, Any]]:
            _CAPTURED.clear()
            _CAPTURED.update(kwargs)
            return rows

    return FakeVM


def test_per_field_filter_flags_build_the_struct() -> None:
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list([{"vm": "vm-1"}]))
    result = runner.invoke(app, ["--power-states", "POWERED_ON", "--names", "web-1"])
    assert result.exit_code == 0, result.stdout
    filt = _CAPTURED["filter"]
    assert list(filt.power_states) == ["POWERED_ON"]
    assert list(filt.names) == ["web-1"]


def test_list_filter_flag_is_repeatable() -> None:
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list([]))
    result = runner.invoke(app, ["--names", "a", "--names", "b"])
    assert result.exit_code == 0, result.stdout
    # names is a vAPI Set field — both values arrive; ordering is not significant.
    assert set(_CAPTURED["filter"].names) == {"a", "b"}


def test_raw_filter_blob_is_base_and_flags_override() -> None:
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list([]))
    result = runner.invoke(
        app, ["--filter", '{"clusters": ["domain-c1"], "names": ["old"]}', "--names", "web-1"]
    )
    assert result.exit_code == 0, result.stdout
    filt = _CAPTURED["filter"]
    assert list(filt.clusters) == ["domain-c1"]  # unflagged field kept from blob
    assert list(filt.names) == ["web-1"]  # flag wins over blob


def test_bare_list_omits_filter_kwarg() -> None:
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list([]))
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.stdout
    assert "filter" not in _CAPTURED


def test_enum_filter_flag_rejects_bad_choice() -> None:
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list([]))
    result = runner.invoke(app, ["--power-states", "ON_FIRE"])
    assert result.exit_code == 2  # invalid enum value rejected as usage error


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #


class _ListResult(dict):
    """Stand-in for an NSX ``*ListResult``: attribute access (like a VapiStruct)
    plus dict rendering (so ``jsonable`` serializes it exactly like the real one)."""

    def __init__(self, results: list[dict[str, Any]], cursor: str | None, result_count: int = 0):
        super().__init__(results=results, cursor=cursor, result_count=result_count)
        self.results = results
        self.cursor = cursor
        self.result_count = result_count


def _fake_segments(pages: dict[str | None, _ListResult]) -> type:
    class FakeSeg:
        def __init__(self, _cfg: object) -> None:
            pass

        def __getattr__(self, _name: str) -> Any:
            # The real NSX list method has an opaque op-id name; route any call to it.
            def method(**kwargs: Any) -> _ListResult:
                return pages[kwargs.get("cursor")]

            return method

    return FakeSeg


def test_nsx_list_all_follows_cursor_and_concatenates() -> None:
    pages = {
        None: _ListResult([{"id": "s1"}, {"id": "s2"}], "c1"),
        "c1": _ListResult([{"id": "s3"}], None),
    }
    app = _app(_op("Segments", "nsx", "list"), _fake_segments(pages))
    result = runner.invoke(app, ["--all"])
    assert result.exit_code == 0, result.stdout
    out = json.loads(result.stdout)
    assert [r["id"] for r in out["results"]] == ["s1", "s2", "s3"]
    assert out["result_count"] == 3


def test_nsx_list_all_respects_max_items() -> None:
    pages = {
        None: _ListResult([{"id": "s1"}, {"id": "s2"}], "c1"),
        "c1": _ListResult([{"id": "s3"}], None),
    }
    app = _app(_op("Segments", "nsx", "list"), _fake_segments(pages))
    result = runner.invoke(app, ["--all", "--max-items", "2"])
    out = json.loads(result.stdout)
    assert out["result_count"] == 2
    assert [r["id"] for r in out["results"]] == ["s1", "s2"]


def test_nsx_single_page_preserves_cursor() -> None:
    pages = {None: _ListResult([{"id": "s1"}], "next-cur", result_count=10)}
    app = _app(_op("Segments", "nsx", "list"), _fake_segments(pages))
    result = runner.invoke(app, [])  # no --all
    out = json.loads(result.stdout)
    assert out["cursor"] == "next-cur"  # cursor surfaced for manual paging


def test_vsphere_limit_caps_plain_list() -> None:
    rows = [{"vm": f"vm-{i}"} for i in range(5)]
    app = _app(_op("VM", "vsphere", "list"), _fake_vm_list(rows))
    result = runner.invoke(app, ["--limit", "2"])
    out = json.loads(result.stdout)
    assert len(out) == 2
