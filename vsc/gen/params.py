"""Map vAPI binding ``Type`` objects to the :class:`Param` model and coerce CLI
input back into the values the SDK call expects.

The vAPI runtime performs *no* string coercion: integers, booleans, datetimes,
and ``set`` vs ``list`` must already be the right Python type when handed to a
generated operation method. This module owns that conversion.

Key rules (verified against the installed SDK):

* ``OptionalType`` wraps optional fields — unwrap and treat as not-required.
* ``ReferenceType`` is lazy — always resolve via ``.resolved_type`` *before*
  classifying; enums and nested structs hide behind it.
* ``SetType`` needs a real ``set``; ``ListType`` a ``list`` — not interchangeable.
* ``datetime`` must be timezone-aware.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import vmware.vapi.bindings.type as bt

from vsc.gen.model import SCALAR_KINDS, Param, ParamKind


class CoercionError(ValueError):
    """Raised when a CLI value cannot be coerced to the SDK type."""


def _unwrap(ftype: Any) -> tuple[bool, Any]:
    """Return ``(required, core_type)`` with Optional/Reference unwrapped."""
    required = not isinstance(ftype, bt.OptionalType)
    core = ftype.element_type if isinstance(ftype, bt.OptionalType) else ftype
    if isinstance(core, bt.ReferenceType):
        core = core.resolved_type
    return required, core


def _enum_values(core: Any) -> list[str]:
    vals = getattr(core, "values", None)
    if not vals:
        return []
    return [str(v) for v in vals]


def _kind_of(core: Any) -> ParamKind:
    """Classify an already-unwrapped core vAPI type into a :class:`ParamKind`."""
    # Order matters: more specific subclasses first.
    if isinstance(core, bt.SecretType):
        return ParamKind.SECRET
    if isinstance(core, bt.IdType):
        return ParamKind.ID
    if isinstance(core, bt.URIType):
        return ParamKind.URI
    if isinstance(core, bt.EnumType):
        return ParamKind.ENUM
    if isinstance(core, bt.StringType):
        return ParamKind.STRING
    if isinstance(core, bt.IntegerType):
        return ParamKind.INTEGER
    if isinstance(core, bt.DoubleType):
        return ParamKind.DOUBLE
    if isinstance(core, bt.BooleanType):
        return ParamKind.BOOLEAN
    if isinstance(core, bt.DateTimeType):
        return ParamKind.DATETIME
    if isinstance(core, bt.SetType):
        return ParamKind.SET
    if isinstance(core, bt.ListType):
        return ParamKind.LIST
    if isinstance(core, bt.MapType):
        return ParamKind.MAP
    if isinstance(core, bt.BlobType):
        return ParamKind.BLOB
    if isinstance(core, bt.StructType):
        return ParamKind.STRUCT
    # DynamicStructType, OpaqueType, AnyType, etc.
    return ParamKind.DYNAMIC


def param_from_type(
    name: str,
    ftype: Any,
    *,
    path_vars: tuple[str, ...] = (),
    query_vars: frozenset[str] = frozenset(),
    body_param: str | None = None,
) -> Param:
    """Build a :class:`Param` from a vAPI field ``Type`` (recursively)."""
    required, core = _unwrap(ftype)
    kind = _kind_of(core)
    p = Param(
        name=name,
        kind=kind,
        required=required,
        in_path=name in path_vars,
        in_query=name in query_vars,
        is_body=(name == body_param),
        raw_type=core,
    )
    if kind is ParamKind.ENUM:
        p.enum_values = _enum_values(core)
    elif kind is ParamKind.ID:
        p.resource_types = _first_resource_type(core)
    elif kind in (ParamKind.LIST, ParamKind.SET):
        p.element = param_from_type("", core.element_type)
    elif kind is ParamKind.MAP:
        p.key_kind = _kind_of(_unwrap(core.key_type)[1])
        p.value_kind = _kind_of(_unwrap(core.value_type)[1])
    elif kind is ParamKind.STRUCT:
        p.struct_name = getattr(core, "name", None)
        p.struct_class = getattr(core, "binding_class", None)
    return p


def _first_resource_type(core: Any) -> str | None:
    rt = getattr(core, "resource_types", None)
    if isinstance(rt, str):
        return rt
    if isinstance(rt, (list, tuple)) and rt:
        return str(rt[0])
    return None


# --------------------------------------------------------------------------- #
# Coercion: CLI value -> SDK value
# --------------------------------------------------------------------------- #


def coerce_scalar(kind: ParamKind, value: Any) -> Any:
    """Coerce a single scalar CLI value to the SDK-expected Python type."""
    if value is None:
        return None
    if kind in (
        ParamKind.STRING,
        ParamKind.ID,
        ParamKind.SECRET,
        ParamKind.URI,
        ParamKind.ENUM,
    ):
        return str(value)
    if kind is ParamKind.INTEGER:
        return value if isinstance(value, int) else int(str(value))
    if kind is ParamKind.DOUBLE:
        return value if isinstance(value, float) else float(str(value))
    if kind is ParamKind.BOOLEAN:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if kind is ParamKind.DATETIME:
        dt = value if isinstance(value, _dt.datetime) else _dt.datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=_dt.UTC)
    return value


def coerce_value(param: Param, value: Any) -> Any:
    """Coerce a CLI value into the SDK value for ``param`` (recursive)."""
    if value is None:
        return None
    kind = param.kind
    if kind in SCALAR_KINDS:
        return coerce_scalar(kind, value)
    if kind in (ParamKind.LIST, ParamKind.SET):
        items = _as_sequence(value)
        element = param.element
        coerced = [coerce_value(element, v) if element else v for v in items]
        return set(coerced) if kind is ParamKind.SET else coerced
    if kind is ParamKind.MAP:
        obj = value if isinstance(value, dict) else json.loads(str(value))
        if not isinstance(obj, dict):
            raise CoercionError(f"{param.name!r}: expected a JSON object")
        return {
            coerce_scalar(param.key_kind or ParamKind.STRING, k): coerce_scalar(
                param.value_kind or ParamKind.STRING, v
            )
            for k, v in obj.items()
        }
    if kind is ParamKind.STRUCT:
        obj = value if isinstance(value, dict) else json.loads(str(value))
        if not isinstance(obj, dict):
            raise CoercionError(f"{param.name!r}: expected a JSON object")
        return coerce_struct(param, obj)
    # DYNAMIC / BLOB: parse JSON if it looks like JSON, else pass through.
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (ValueError, TypeError):
        return value


def coerce_struct(param: Param, obj: dict[str, Any]) -> Any:
    """Build the struct's ``binding_class`` from a JSON object, coercing fields."""
    struct_type = param.raw_type
    struct_class = param.struct_class
    if struct_class is None or struct_type is None:
        # No binding class resolved — hand the dict to the runtime as-is.
        return obj
    field_names = set(struct_type.get_field_names())
    kwargs: dict[str, Any] = {}
    for key, raw_value in obj.items():
        if key not in field_names:
            raise CoercionError(f"{param.name!r}: unknown field {key!r}")
        field_param = param_from_type(key, struct_type.get_field(key))
        kwargs[key] = coerce_value(field_param, raw_value)
    return struct_class(**kwargs)


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return parsed
        return [value]
    return [value]
