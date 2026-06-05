"""Turn :class:`Operation` objects into Typer commands and assemble the tree.

Each generated command builds its own ``inspect.Signature`` so Typer can derive
options/arguments dynamically. Connections are resolved lazily through an injected
``connect_for_backend`` callable, keeping tree assembly and ``--help`` offline.
"""

from __future__ import annotations

import inspect
import keyword
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
import typer
from vmware.vapi.exception import CoreException

from vsc.config.store import ConfigError
from vsc.connect.targets import TargetNotConfigured
from vsc.gen.complete import enum_completer, output_format_completer
from vsc.gen.filters import assemble_filter, flatten_filter, is_filter_param
from vsc.gen.model import Operation, Param, ParamKind
from vsc.gen.paginate import follow_cursor
from vsc.gen.params import CoercionError, coerce_value
from vsc.gen.preview import build_request_plan
from vsc.output.errors import (
    envelope_for_transport,
    envelope_for_vapi,
    is_vapi_error,
    render_error,
)
from vsc.output.exit_codes import ExitCode
from vsc.output.render import OutputFormat, emit, emit_request, jsonable

ConnectFn = Callable[[str], Any]

_OUTPUT_PARAM = "_vsc_output"
_APPLY_PARAM = "_vsc_apply"
# Pagination options injected on list commands (read-only).
_ALL_PARAM = "_vsc_all"
_MAXITEMS_PARAM = "_vsc_max_items"
_LIMIT_PARAM = "_vsc_limit"

# User-facing option names the generator injects itself; a real SDK parameter with
# one of these names is renamed so it can't shadow --output / --apply.
_RESERVED_OPTION_NAMES = frozenset({"output", "apply"})


@dataclass
class FilterPlan:
    """How a list op's ``filter`` struct is exposed and reassembled.

    The struct stays available as a raw ``--filter '<json>'`` option (``sig_name``)
    and is *also* flattened into per-field ``--<field>`` options (``fields``); at
    invocation the flag values merge over the blob and coerce back into the struct.
    """

    param: Param
    sig_name: str
    fields: list[tuple[Param, str]]

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
    reserved = name in (_OUTPUT_PARAM, _APPLY_PARAM) or name in _RESERVED_OPTION_NAMES
    if keyword.iskeyword(name) or reserved or name in used:
        name = f"{name}_"
    used.add(name)
    return name


def _autocompletion_for(param: Param) -> Callable[[str], list[str]] | None:
    """Offline completer for an option: enum choices, or a list-of-enum's choices."""
    if param.kind is ParamKind.ENUM and param.enum_values:
        return enum_completer(param.enum_values)
    element = param.element
    if (
        param.kind in (ParamKind.LIST, ParamKind.SET)
        and element is not None
        and element.kind is ParamKind.ENUM
        and element.enum_values
    ):
        return enum_completer(element.enum_values)
    return None


def _option_parameter(param: Param, sig_name: str) -> inspect.Parameter:
    """Build the ``inspect.Parameter`` for a non-path option."""
    # A param named output/apply would otherwise emit --output/--apply and clash
    # with the injected options; use the suffixed sig name for those.
    opt_source = sig_name if param.name in _RESERVED_OPTION_NAMES else param.name
    kebab = opt_source.replace("_", "-")
    # Boolean options need a dual flag so the user can send False, not just True.
    opt = f"--{kebab}/--no-{kebab}" if param.kind is ParamKind.BOOLEAN else f"--{kebab}"
    default = typer.Option(
        ... if param.required else None,
        opt,
        help=_help_text(param),
        hide_input=param.kind is ParamKind.SECRET,
        autocompletion=_autocompletion_for(param),
    )
    return inspect.Parameter(
        sig_name,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=default,
        annotation=_annotation(param),
    )


def _build_filter_options(
    filter_param: Param, used: set[str], parameters: list[inspect.Parameter]
) -> FilterPlan:
    """Emit the raw ``--filter`` option plus one ``--<field>`` option per struct field."""
    raw_sig = _sig_name(filter_param, used)
    parameters.append(_option_parameter(filter_param, raw_sig))
    fields: list[tuple[Param, str]] = []
    for child in flatten_filter(filter_param):
        child_sig = _sig_name(child, used)
        parameters.append(_option_parameter(child, child_sig))
        fields.append((child, child_sig))
    return FilterPlan(param=filter_param, sig_name=raw_sig, fields=fields)


def _build_signature(
    op: Operation,
) -> tuple[inspect.Signature, list[tuple[Param, str]], FilterPlan | None]:
    parameters: list[inspect.Parameter] = []
    spec: list[tuple[Param, str]] = []
    used: set[str] = set()
    filter_plan: FilterPlan | None = None
    # Stable order: required path args first, then everything else.
    ordered = sorted(op.params, key=lambda p: (not (p.in_path and p.required), p.name))
    for param in ordered:
        if is_filter_param(param):
            # Flattened into per-field flags + raw --filter; reassembled at call time.
            filter_plan = _build_filter_options(param, used, parameters)
            continue
        sig_name = _sig_name(param, used)
        default: Any
        if param.in_path:
            default = typer.Argument(... if param.required else None, help=_help_text(param))
            parameters.append(
                inspect.Parameter(
                    sig_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=default,
                    annotation=_annotation(param),
                )
            )
        else:
            parameters.append(_option_parameter(param, sig_name))
        spec.append((param, sig_name))
    parameters.append(
        inspect.Parameter(
            _OUTPUT_PARAM,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Option(
                OutputFormat.json,
                "--output",
                "-o",
                help="Output format.",
                autocompletion=output_format_completer(),
            ),
            annotation=OutputFormat,
        )
    )
    if op.is_write:
        # Writes preview by default; --apply opts in to actually executing.
        parameters.append(
            inspect.Parameter(
                _APPLY_PARAM,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=typer.Option(
                    False, "--apply/--no-apply", help="Execute the change (default: dry-run)."
                ),
                annotation=bool,
            )
        )
    elif op.cli_verb == "list":
        parameters.extend(_paging_parameters())
    return inspect.Signature(parameters), spec, filter_plan


def _paging_parameters() -> list[inspect.Parameter]:
    """The ``--all`` / ``--max-items`` / ``--limit`` options injected on list commands."""

    def _opt(name: str, default: Any, decl: str, help_text: str, ann: Any) -> inspect.Parameter:
        return inspect.Parameter(
            name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Option(default, decl, help=help_text),
            annotation=ann,
        )

    return [
        _opt(
            _ALL_PARAM,
            False,
            "--all",
            "Follow the cursor and return every page (paginated backends, e.g. NSX).",
            bool,
        ),
        _opt(_MAXITEMS_PARAM, None, "--max-items", "Cap the total number of items returned.", int),
        _opt(
            _LIMIT_PARAM,
            None,
            "--limit",
            "Client-side cap for non-paginated (vSphere) lists.",
            int,
        ),
    ]


def make_command(op: Operation, connect_fn: ConnectFn) -> Callable[..., None]:
    """Build a Typer-compatible callback for ``op``."""
    signature, spec, filter_plan = _build_signature(op)

    def command(**kwargs: Any) -> None:
        raw_fmt = kwargs.get(_OUTPUT_PARAM, OutputFormat.json)
        fmt = raw_fmt.value if isinstance(raw_fmt, OutputFormat) else str(raw_fmt)
        apply = bool(kwargs.get(_APPLY_PARAM, False))
        # Coerce inputs and resolve the write plan up front. Building the plan
        # serializes the request body, so a malformed/incomplete struct surfaces
        # here as a clean usage error (exit 2) — before any connection — rather
        # than leaking a vAPI traceback. CoreException is the SDK's client-side
        # validation/serialization error.
        try:
            sdk_kwargs = _collect_kwargs(spec, kwargs)
            if filter_plan is not None:
                _apply_filter(filter_plan, kwargs, sdk_kwargs)
            plan = build_request_plan(op, sdk_kwargs) if op.is_write else None
        except (CoercionError, CoreException) as exc:
            _fail_usage(exc, fmt)
            return
        # Dry-run by default: preview the resolved request and touch nothing — no
        # connection is opened unless the write is explicitly applied.
        if op.is_write and not apply:
            assert plan is not None  # guaranteed: op.is_write -> plan built above
            emit_request(plan, applied=False, fmt=fmt)
            return
        try:
            cfg = connect_fn(op.backend)
            service = op.service_cls(cfg)
            method = getattr(service, op.method_name, None)
            invoke = method if callable(method) else _invoker(service, op.op_id)
            if op.cli_verb == "list" and not op.is_write:
                result = _run_list(
                    invoke,
                    sdk_kwargs,
                    all_flag=bool(kwargs.get(_ALL_PARAM, False)),
                    max_items=kwargs.get(_MAXITEMS_PARAM),
                    limit=kwargs.get(_LIMIT_PARAM),
                )
                emit(result, fmt)
            elif op.is_write:
                assert plan is not None  # guaranteed: op.is_write -> plan built above
                emit_request(plan, applied=True, result=invoke(**sdk_kwargs), fmt=fmt)
            else:
                emit(invoke(**sdk_kwargs), fmt)
        except TargetNotConfigured as exc:
            _fail_config(exc, fmt)
        except ConfigError as exc:
            _fail(ExitCode.CONFIG, "ConfigError", exc, fmt)
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


def _invoker(service: Any, op_id: str) -> Callable[..., Any]:
    """Fallback invoker for services that don't expose a bound method by name."""

    def invoke(**kwargs: Any) -> Any:
        return service._invoke(op_id, kwargs)

    return invoke


def _apply_filter(
    plan: FilterPlan, kwargs: dict[str, Any], sdk_kwargs: dict[str, Any]
) -> None:
    """Merge the raw ``--filter`` blob with per-field flags into the filter kwarg."""
    field_values = {child.name: kwargs.get(sig) for child, sig in plan.fields}
    filt = assemble_filter(kwargs.get(plan.sig_name), field_values, plan.param)
    if filt is not None:
        sdk_kwargs[plan.param.name] = filt


def _is_cursor_list(result: Any) -> bool:
    """True for a paginated list result (carries both ``results`` and ``cursor``)."""
    return hasattr(result, "results") and hasattr(result, "cursor")


def _run_list(
    invoke: Callable[..., Any],
    sdk_kwargs: dict[str, Any],
    *,
    all_flag: bool,
    max_items: int | None,
    limit: int | None,
) -> Any:
    """Execute a list operation, applying ``--all`` / ``--max-items`` / ``--limit``.

    Without any paging flag the raw result is returned unchanged (preserving the
    cursor for manual paging). ``--all`` follows the cursor across pages; the caps
    slice the returned items client-side.
    """
    if all_flag:

        def fetch_page(cursor: str | None) -> tuple[list[Any], str | None]:
            page_kwargs = dict(sdk_kwargs)
            if cursor is not None:
                page_kwargs["cursor"] = cursor
            res = invoke(**page_kwargs)
            if _is_cursor_list(res):
                return list(getattr(res, "results", []) or []), getattr(res, "cursor", None)
            # Non-paginated backend: the whole response is the one and only page.
            items = list(res) if isinstance(res, list) else [res]
            return items, None

        collected = follow_cursor(fetch_page, max_items=max_items)
        return {"results": jsonable(collected), "result_count": len(collected)}

    result = invoke(**sdk_kwargs)
    cap = max_items if max_items is not None else limit
    if _is_cursor_list(result):
        data = jsonable(result)
        if cap is not None and isinstance(data, dict) and isinstance(data.get("results"), list):
            data["results"] = data["results"][:cap]
        return data
    # Plain list (vSphere) or scalar.
    plain_cap = limit if limit is not None else max_items
    if plain_cap is not None and isinstance(result, list):
        return result[:plain_cap]
    return result


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
