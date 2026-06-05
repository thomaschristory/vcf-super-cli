"""Type mapping + coercion tests."""

from __future__ import annotations

import datetime as dt

import pytest
from com.vmware.vcenter.vm_client import Power
from vmware.vapi.bindings.struct import VapiStruct

from vsc.gen.discover import discover_operations, nsx_services, vsphere_services
from vsc.gen.model import Param, ParamKind
from vsc.gen.params import coerce_scalar, coerce_value, param_from_type


def test_coerce_scalars() -> None:
    assert coerce_scalar(ParamKind.INTEGER, "5") == 5
    assert coerce_scalar(ParamKind.DOUBLE, "1.5") == 1.5
    assert coerce_scalar(ParamKind.BOOLEAN, "true") is True
    assert coerce_scalar(ParamKind.BOOLEAN, "no") is False
    assert coerce_scalar(ParamKind.STRING, "x") == "x"
    assert coerce_scalar(ParamKind.ENUM, "POWERED_ON") == "POWERED_ON"


def test_coerce_datetime_is_tz_aware() -> None:
    out = coerce_scalar(ParamKind.DATETIME, "2026-06-05T10:00:00")
    assert isinstance(out, dt.datetime)
    assert out.tzinfo is not None


def test_list_and_set_containers() -> None:
    list_param = Param(
        name="x", kind=ParamKind.LIST, required=False, element=Param("", ParamKind.STRING, False)
    )
    set_param = Param(
        name="y", kind=ParamKind.SET, required=False, element=Param("", ParamKind.STRING, False)
    )
    assert coerce_value(list_param, ["a", "b"]) == ["a", "b"]
    result = coerce_value(set_param, ["a", "a", "b"])
    assert isinstance(result, set)
    assert result == {"a", "b"}


def test_map_from_json() -> None:
    p = Param(
        name="m",
        kind=ParamKind.MAP,
        required=False,
        key_kind=ParamKind.STRING,
        value_kind=ParamKind.STRING,
    )
    assert coerce_value(p, '{"k": "v"}') == {"k": "v"}


def test_none_is_dropped() -> None:
    p = Param(name="x", kind=ParamKind.STRING, required=False)
    assert coerce_value(p, None) is None


def _first_set_field(struct_type: object) -> str | None:
    for name in struct_type.get_field_names():  # type: ignore[attr-defined]
        if param_from_type(name, struct_type.get_field(name)).kind is ParamKind.SET:  # type: ignore[attr-defined]
            return name
    return None


def test_coerce_struct_builds_vapistruct_with_set() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    filt = next(p for o in ops if o.cli_verb == "list" for p in o.params if p.name == "filter")
    field = _first_set_field(filt.raw_type)
    assert field is not None, "expected at least one set field on VM.FilterSpec"
    built = coerce_value(filt, {field: ["a", "b"]})
    assert isinstance(built, VapiStruct)
    assert isinstance(getattr(built, field), set)


def test_coerce_struct_rejects_unknown_field() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    filt = next(p for o in ops if o.cli_verb == "list" for p in o.params if p.name == "filter")
    with pytest.raises(ValueError):
        coerce_value(filt, {"definitely_not_a_field": ["x"]})


def test_struct_invalid_json_raises_coercion_error() -> None:
    ops = discover_operations(vsphere_services()[0], "vsphere")
    filt = next(p for o in ops if o.cli_verb == "list" for p in o.params if p.name == "filter")
    with pytest.raises(ValueError):
        coerce_value(filt, "{not valid json")


def test_enum_values_extracted_from_binding_class() -> None:
    p = param_from_type("state", Power.State.get_binding_type())
    assert p.kind is ParamKind.ENUM
    assert set(p.enum_values) == {"POWERED_OFF", "POWERED_ON", "SUSPENDED"}


def test_scalar_double_and_aware_datetime_passthrough() -> None:
    assert coerce_scalar(ParamKind.DOUBLE, "2.5") == 2.5
    aware = dt.datetime(2026, 6, 5, tzinfo=dt.UTC)
    assert coerce_scalar(ParamKind.DATETIME, aware) is aware


def test_dynamic_kind_parses_json_else_passthrough() -> None:
    p = Param(name="d", kind=ParamKind.DYNAMIC, required=False)
    assert coerce_value(p, '{"a": 1}') == {"a": 1}
    assert coerce_value(p, "plain-string") == "plain-string"


def test_set_from_json_array_string_with_int_elements() -> None:
    p = Param(
        name="ids",
        kind=ParamKind.SET,
        required=False,
        element=Param("", ParamKind.INTEGER, False),
    )
    result = coerce_value(p, "[1, 2, 2]")
    assert result == {1, 2}


def test_map_with_integer_values() -> None:
    p = Param(
        name="m",
        kind=ParamKind.MAP,
        required=False,
        key_kind=ParamKind.STRING,
        value_kind=ParamKind.INTEGER,
    )
    assert coerce_value(p, '{"a": "3"}') == {"a": 3}


# --------------------------------------------------------------------------- #
# v0.2: write-body struct coercion (the path that builds request bodies)
# --------------------------------------------------------------------------- #


def _write_param(service_name: str, verb: str, backend: str, param_name: str) -> Param:
    services = vsphere_services() if backend == "vsphere" else nsx_services()
    cls = next(c for c in services if c.__name__ == service_name)
    op = next(o for o in discover_operations(cls, backend, read_only=False) if o.cli_verb == verb)
    return next(p for p in op.params if p.name == param_name)


def test_nsx_named_body_struct_roundtrip() -> None:
    # NSX flags a single request_body_parameter; it coerces to its binding struct.
    seg = _write_param("Segments", "set", "nsx", "segment")
    assert seg.is_body and seg.kind is ParamKind.STRUCT and seg.struct_class is not None
    built = coerce_value(seg, {"display_name": "web", "description": "d"})
    assert isinstance(built, VapiStruct)
    assert built.display_name == "web"
    assert built.description == "d"


def test_vsphere_spec_body_struct_roundtrip() -> None:
    # vCenter has no flagged body param; the spec struct still coerces field-by-field.
    spec = _write_param("VM", "create", "vsphere", "spec")
    assert spec.kind is ParamKind.STRUCT and not spec.is_body
    built = coerce_value(spec, {"name": "vm-1"})
    assert isinstance(built, VapiStruct)
    assert built.name == "vm-1"


def test_nsx_body_from_json_string_roundtrip() -> None:
    # The body arrives from the CLI as a JSON string; coercion parses then builds.
    seg = _write_param("Segments", "set", "nsx", "segment")
    built = coerce_value(seg, '{"display_name": "web"}')
    assert isinstance(built, VapiStruct)
    assert built.display_name == "web"
