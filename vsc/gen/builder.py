"""Turn :class:`Operation` objects into Typer commands and assemble the tree.

Each generated command builds its own ``inspect.Signature`` so Typer can derive
options/arguments dynamically. Connections are resolved lazily through an injected
``connect_for_backend`` callable, keeping tree assembly and ``--help`` offline.
"""

from __future__ import annotations

import inspect
import keyword
from collections.abc import Callable
from typing import Any

import requests
import typer

from vsc.connect.targets import TargetNotConfigured
from vsc.gen.model import Operation, Param, ParamKind
from vsc.gen.params import CoercionError, coerce_value
from vsc.output.errors import (
    envelope_for_transport,
    envelope_for_vapi,
    is_vapi_error,
    render_error,
)
from vsc.output.exit_codes import ExitCode
from vsc.output.render import OutputFormat, emit

ConnectFn = Callable[[str], Any]

_OUTPUT_PARAM = "_vsc_output"

_ANNOTATIONS: dict[ParamKind, type] = {
    ParamKind.INTEGER: int,
    ParamKind.DOUBLE: float,
    ParamKind.BOOLEAN: bool,
}


def _annotation(param: Param) -> Any:
    if param.kind in (ParamKind.LIST, ParamKind.SET):
        base: Any = list[str]
    else:
        base = _ANNOTATIONS.get(param.kind, str)
    return base if param.required else (base | None)


def _help_text(param: Param) -> str:
    bits: list[str] = [param.kind.value]
    if param.kind is ParamKind.ENUM and param.enum_values:
        bits.append("choices: " + ", ".join(param.enum_values))
    if param.kind is ParamKind.ID and param.resource_types:
        bits.append(f"id of {param.resource_types}")
    if param.kind in (ParamKind.STRUCT, ParamKind.MAP, ParamKind.DYNAMIC):
        bits.append("JSON")
    return "; ".join(bits)


def _sig_name(param: Param, used: set[str]) -> str:
    name = param.name
    if keyword.iskeyword(name) or name == _OUTPUT_PARAM or name in used:
        name = f"{name}_"
    used.add(name)
    return name


def _build_signature(op: Operation) -> tuple[inspect.Signature, list[tuple[Param, str]]]:
    parameters: list[inspect.Parameter] = []
    spec: list[tuple[Param, str]] = []
    used: set[str] = set()
    # Stable order: required path args first, then everything else.
    ordered = sorted(op.params, key=lambda p: (not (p.in_path and p.required), p.name))
    for param in ordered:
        sig_name = _sig_name(param, used)
        help_text = _help_text(param)
        default: Any
        if param.in_path:
            default = typer.Argument(... if param.required else None, help=help_text)
        else:
            kebab = param.name.replace("_", "-")
            # Boolean options need a dual flag so the user can send False, not
            # just True; otherwise only the positive flag exists.
            opt = f"--{kebab}/--no-{kebab}" if param.kind is ParamKind.BOOLEAN else f"--{kebab}"
            default = typer.Option(
                ... if param.required else None,
                opt,
                help=help_text,
                hide_input=param.kind is ParamKind.SECRET,
            )
        parameters.append(
            inspect.Parameter(
                sig_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=_annotation(param),
            )
        )
        spec.append((param, sig_name))
    parameters.append(
        inspect.Parameter(
            _OUTPUT_PARAM,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Option(OutputFormat.json, "--output", "-o", help="Output format."),
            annotation=OutputFormat,
        )
    )
    return inspect.Signature(parameters), spec


def make_command(op: Operation, connect_fn: ConnectFn) -> Callable[..., None]:
    """Build a Typer-compatible callback for ``op``."""
    signature, spec = _build_signature(op)

    def command(**kwargs: Any) -> None:
        raw_fmt = kwargs.get(_OUTPUT_PARAM, OutputFormat.json)
        fmt = raw_fmt.value if isinstance(raw_fmt, OutputFormat) else str(raw_fmt)
        try:
            sdk_kwargs = _collect_kwargs(spec, kwargs)
        except CoercionError as exc:
            _fail_usage(exc, fmt)
            return
        try:
            cfg = connect_fn(op.backend)
            service = op.service_cls(cfg)
            method = getattr(service, op.method_name, None)
            if callable(method):
                result = method(**sdk_kwargs)
            else:
                result = service._invoke(op.op_id, sdk_kwargs)
            emit(result, fmt)
        except TargetNotConfigured as exc:
            _fail_config(exc, fmt)
        except requests.exceptions.RequestException as exc:
            env, code = envelope_for_transport(exc)
            render_error(env, fmt)
            raise typer.Exit(int(code)) from exc
        except Exception as exc:
            if not is_vapi_error(exc):
                raise
            env, code = envelope_for_vapi(exc)
            render_error(env, fmt)
            raise typer.Exit(int(code)) from exc

    command.__signature__ = signature  # type: ignore[attr-defined]
    command.__name__ = op.cli_verb.replace("-", "_")
    command.__doc__ = f"{op.http_method} {op.url_template}"
    return command


def _collect_kwargs(spec: list[tuple[Param, str]], kwargs: dict[str, Any]) -> dict[str, Any]:
    sdk_kwargs: dict[str, Any] = {}
    for param, sig_name in spec:
        value = kwargs.get(sig_name)
        if value is None:
            continue
        if param.kind is ParamKind.ENUM and param.enum_values and value not in param.enum_values:
            raise CoercionError(
                f"{param.name!r}: {value!r} not in {{{', '.join(param.enum_values)}}}"
            )
        sdk_kwargs[param.name] = coerce_value(param, value)
    return sdk_kwargs


def _fail(code: ExitCode, kind: str, exc: Exception, fmt: str) -> None:
    env = {"error": {"code": int(code), "kind": kind, "message": str(exc), "details": None}}
    render_error(env, fmt)
    raise typer.Exit(int(code)) from exc


def _fail_config(exc: Exception, fmt: str) -> None:
    _fail(ExitCode.CONFIG, "TargetNotConfigured", exc, fmt)


def _fail_usage(exc: Exception, fmt: str) -> None:
    _fail(ExitCode.USAGE, "InvalidArgument", exc, fmt)


def build_group(operations: list[Operation], connect_fn: ConnectFn) -> typer.Typer:
    """Assemble operations for one backend into a Typer app of service groups."""
    services: dict[str, typer.Typer] = {}
    used_names: dict[str, set[str]] = {}
    for op in operations:
        short = op.service_short.replace("_", "-")
        group = services.get(short)
        if group is None:
            group = typer.Typer(no_args_is_help=True, help=f"{short} operations.")
            services[short] = group
            used_names[short] = set()
        name = op.cli_verb
        if name in used_names[short]:
            name = op.op_id.replace("_", "-").replace("$", "-")
        used_names[short].add(name)
        group.command(name, help=f"{op.http_method} {op.url_template}")(
            make_command(op, connect_fn)
        )
    root = typer.Typer(no_args_is_help=True)
    for short, group in sorted(services.items()):
        root.add_typer(group, name=short)
    return root
