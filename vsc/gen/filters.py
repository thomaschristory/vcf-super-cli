"""Flatten a list operation's ``filter`` struct into per-field CLI flags.

vCenter list operations take a single ``filter`` parameter that is a struct
(``VM.FilterSpec`` etc.). v0.1/v0.2 exposed it only as a raw ``--filter '<json>'``
blob. Here we additionally flatten its fields into typed ``--<field>`` options and
reassemble them — merged over any raw blob — back into the struct the SDK expects.

The blob stays the base layer and escape hatch; per-field flags win over it. All
type coercion is delegated to :mod:`vsc.gen.params`, so this module only handles
field discovery and the merge.
"""

from __future__ import annotations

import json
from typing import Any

from vsc.gen.model import Param, ParamKind
from vsc.gen.params import CoercionError, coerce_value, param_from_type


def is_filter_param(param: Param) -> bool:
    """True for the flattenable ``filter`` struct (not a write-body struct)."""
    return param.kind is ParamKind.STRUCT and param.name == "filter" and param.raw_type is not None


def flatten_filter(param: Param) -> list[Param]:
    """Return one child :class:`Param` per field of the filter struct."""
    struct_type = param.raw_type
    return [
        param_from_type(name, struct_type.get_field(name))
        for name in struct_type.get_field_names()
    ]


def _parse_base(base_json: str | None) -> dict[str, Any]:
    if not base_json:
        return {}
    try:
        obj = json.loads(base_json)
    except (ValueError, TypeError) as exc:
        raise CoercionError(f"'filter': invalid JSON ({exc})") from exc
    if not isinstance(obj, dict):
        raise CoercionError("'filter': expected a JSON object")
    return obj


def _check_enum(child: Param | None, value: Any) -> None:
    """Reject a per-field flag value that isn't a valid enum choice."""
    if child is None:
        return
    if child.kind is ParamKind.ENUM and child.enum_values:
        if str(value) not in child.enum_values:
            raise CoercionError(
                f"{child.name!r}: {value!r} not in {{{', '.join(child.enum_values)}}}"
            )
    elif (
        child.kind in (ParamKind.LIST, ParamKind.SET)
        and child.element is not None
        and child.element.kind is ParamKind.ENUM
        and child.element.enum_values
    ):
        for item in value:
            if str(item) not in child.element.enum_values:
                raise CoercionError(
                    f"{child.name!r}: {item!r} not in {{{', '.join(child.element.enum_values)}}}"
                )


def assemble_filter(
    base_json: str | None, field_values: dict[str, Any], param: Param
) -> Any | None:
    """Merge the raw ``--filter`` blob with per-field flag values and coerce.

    Per-field values (already keyed by struct field name; ``None`` means the flag
    was not supplied) override matching keys in the JSON base. Enum flags are
    validated against their choices. Returns the coerced filter struct, or ``None``
    when nothing was supplied so the caller can omit the ``filter`` kwarg entirely.
    """
    merged = dict(_parse_base(base_json))
    children = {child.name: child for child in flatten_filter(param)}
    for key, value in field_values.items():
        if value is None:
            continue
        _check_enum(children.get(key), value)
        merged[key] = value
    if not merged:
        return None
    return coerce_value(param, merged)
