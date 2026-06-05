"""Shared execution + error mapping for the pyVmomi fallback commands.

Each command supplies a ``build(si)`` that runs its read against the connected
``ServiceInstance`` and returns a JSON-able result. ``run_read`` centralizes the
connect, the emit, and the mapping of pyVmomi faults / transport errors onto the
project's stable error envelope and exit codes.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from typing import Any

import typer
from pyVmomi import vmodl

from vsc.connect.targets import TargetNotConfigured
from vsc.connect.vmomi import connect_vmomi
from vsc.output.errors import envelope_for_transport, envelope_for_vmomi, render_error
from vsc.output.exit_codes import ExitCode
from vsc.output.render import emit


def _emit_error(fmt: str, env: dict[str, Any], code: ExitCode, exc: BaseException) -> None:
    render_error(env, fmt)
    raise typer.Exit(int(code)) from exc


def _fail(fmt: str, code: ExitCode, kind: str, message: str, exc: BaseException) -> None:
    env = {"error": {"code": int(code), "kind": kind, "message": message, "details": None}}
    _emit_error(fmt, env, code, exc)


def run_read(fmt: str, build: Callable[[Any], Any]) -> None:
    """Connect, run ``build(si)``, and emit — mapping failures to the error envelope."""
    try:
        si = connect_vmomi()
        result = build(si)
    except TargetNotConfigured as exc:
        _fail(fmt, ExitCode.CONFIG, "TargetNotConfigured", str(exc), exc)
    except ValueError as exc:
        # Bad user input surfaced by a command (e.g. an unknown metric name).
        _fail(fmt, ExitCode.USAGE, "InvalidArgument", str(exc), exc)
    except vmodl.MethodFault as exc:
        _emit_error(fmt, *envelope_for_vmomi(exc), exc)
    except (ssl.SSLError, OSError) as exc:
        # SmartConnect transport failures (DNS, refused, TLS) before the SOAP layer.
        _emit_error(fmt, *envelope_for_transport(exc), exc)
    else:
        emit(result, fmt)
