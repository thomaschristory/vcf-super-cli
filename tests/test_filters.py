"""Per-field filter flag flattening and reassembly (pure, offline introspection)."""

from __future__ import annotations

import pytest

from vsc.gen.discover import discover_operations, vsphere_services
from vsc.gen.filters import assemble_filter, flatten_filter, is_filter_param
from vsc.gen.model import Param, ParamKind
from vsc.gen.params import CoercionError


def _vm_filter_param() -> Param:
    vm = next(c for c in vsphere_services() if c.__name__ == "VM")
    listop = next(o for o in discover_operations(vm, "vsphere") if o.cli_verb == "list")
    return next(p for p in listop.params if p.name == "filter")


def test_is_filter_param_identifies_the_filter_struct() -> None:
    filt = _vm_filter_param()
    assert is_filter_param(filt)
    assert not is_filter_param(Param(name="filter", kind=ParamKind.STRING, required=False))
    assert not is_filter_param(Param(name="spec", kind=ParamKind.STRUCT, required=False))


def test_flatten_yields_one_child_per_struct_field() -> None:
    children = flatten_filter(_vm_filter_param())
    names = {c.name for c in children}
    # The VM.FilterSpec fields (verified against the installed SDK).
    assert {"vms", "names", "power_states", "clusters", "hosts"} <= names
    # power_states is a list of an enum, exposed with its choices for completion.
    power = next(c for c in children if c.name == "power_states")
    assert power.kind in (ParamKind.LIST, ParamKind.SET)
    assert power.element is not None and power.element.kind is ParamKind.ENUM
    assert power.element.enum_values  # choices present


def test_assemble_from_field_values_only() -> None:
    filt = _vm_filter_param()
    spec = assemble_filter(None, {"power_states": ["POWERED_ON"], "names": ["web-1"]}, filt)
    assert spec is not None
    assert list(spec.power_states) == ["POWERED_ON"]
    assert list(spec.names) == ["web-1"]


def test_field_values_override_base_blob() -> None:
    filt = _vm_filter_param()
    spec = assemble_filter('{"names": ["from-blob"]}', {"names": ["web-1"]}, filt)
    assert list(spec.names) == ["web-1"]  # per-field flag wins over the JSON base


def test_base_blob_supplies_unflagged_fields() -> None:
    filt = _vm_filter_param()
    spec = assemble_filter('{"clusters": ["domain-c1"]}', {"power_states": ["POWERED_ON"]}, filt)
    assert list(spec.clusters) == ["domain-c1"]
    assert list(spec.power_states) == ["POWERED_ON"]


def test_assemble_returns_none_when_nothing_supplied() -> None:
    # A bare `list` with no filter at all must omit the filter kwarg entirely.
    assert assemble_filter(None, {}, _vm_filter_param()) is None


def test_assemble_rejects_malformed_base_json() -> None:
    with pytest.raises(CoercionError):
        assemble_filter("{not json", {}, _vm_filter_param())
