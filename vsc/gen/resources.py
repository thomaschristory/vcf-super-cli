"""Correlate a vAPI ``resource_type`` with the list operation that enumerates it.

An ``ID``-kind :class:`~vsc.gen.model.Param` carries a ``resource_types`` tag
(e.g. ``VirtualMachine``, ``HostSystem``). To suggest *real* ids at ``<TAB>`` we
need, for each such type, the introspected **list** operation that returns those
ids plus which element fields hold the id and a human label.

This module derives that mapping purely from the offline SDK metadata
(:func:`~vsc.gen.discover.discover_all`) — no network. The heuristic:

* group operations by service;
* a service's *source* list op is its ``list`` verb **with no required path
  argument** (a list that needs a parent id, e.g. a VM's disks, is a
  sub-resource and is deliberately excluded — completing it standalone is
  meaningless);
* the id field is the name of the by-id path parameter that carries the
  ``resource_type`` (the ids in the list share that field name), falling back to
  the first field of the list op's result element when no by-id op exists;
* the name field is ``name`` when the result element exposes one.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any

from vsc.gen.discover import discover_all
from vsc.gen.model import Operation, ParamKind


@dataclass(frozen=True)
class ResourceSource:
    """Where the ids for one ``resource_type`` come from."""

    backend: str
    service_cls: type
    list_op: Operation
    id_field: str
    name_field: str | None


def _elem_fields(list_op: Operation) -> list[str] | None:
    """Field names of a list op's result *element* struct, or ``None``.

    Unwraps the output ``Optional``/``List``/``Reference`` layers to reach the
    element ``StructType``; any structure we don't recognise yields ``None`` so
    the caller falls back to the by-id parameter name.
    """
    cur: Any = list_op.output_type
    for _ in range(6):
        if cur is None:
            return None
        if hasattr(cur, "get_field_names"):
            try:
                return [str(f) for f in cur.get_field_names()]
            except Exception:
                return None
        cur = getattr(cur, "element_type", None) or getattr(cur, "resolved_type", None)
    return None


def _source_list_op(ops: list[Operation]) -> Operation | None:
    """The ``list`` op for a service that can be called with no parent id."""
    for op in ops:
        if op.cli_verb != "list":
            continue
        if any(p.in_path and p.required for p in op.params):
            continue  # sub-resource list (needs a parent id) — not a source
        return op
    return None


def build_resource_registry(
    operations: list[Operation] | None = None,
) -> dict[str, ResourceSource]:
    """Map every resolvable ``resource_type`` to its :class:`ResourceSource`.

    Pass ``operations`` to build from a known op list (tests); otherwise the
    full offline discovery is used.
    """
    ops = operations if operations is not None else discover_all()

    groups: dict[tuple[str, str], list[Operation]] = {}
    for op in ops:
        groups.setdefault((op.backend, op.iface_id), []).append(op)

    registry: dict[str, ResourceSource] = {}
    for (backend, _iface), group in groups.items():
        list_op = _source_list_op(group)
        if list_op is None:
            continue
        elem_fields = _elem_fields(list_op)
        name_field = "name" if elem_fields and "name" in elem_fields else None
        # Prefer the by-id path parameter's name (it names the id field in the
        # list result); fall back to the first result-element field.
        by_id_name: dict[str, str] = {}
        resource_types: set[str] = set()
        for op in group:
            for param in op.params:
                if param.kind is ParamKind.ID and param.resource_types:
                    resource_types.add(param.resource_types)
                    if param.in_path:
                        by_id_name.setdefault(param.resource_types, param.name)
        for rt in resource_types:
            id_field = by_id_name.get(rt) or (elem_fields[0] if elem_fields else None)
            if id_field is None:
                continue  # can't determine which field holds the id — skip
            registry.setdefault(
                rt,
                ResourceSource(
                    backend=backend,
                    service_cls=list_op.service_cls,
                    list_op=list_op,
                    id_field=id_field,
                    name_field=name_field,
                ),
            )
    return registry


@functools.lru_cache(maxsize=1)
def _default_registry() -> dict[str, ResourceSource]:
    return build_resource_registry()


def resource_source(
    resource_type: str, operations: list[Operation] | None = None
) -> ResourceSource | None:
    """Look up the :class:`ResourceSource` for ``resource_type`` (or ``None``)."""
    if operations is not None:
        registry = build_resource_registry(operations)
    else:
        registry = _default_registry()
    return registry.get(resource_type)
