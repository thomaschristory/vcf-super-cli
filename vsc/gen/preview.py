"""Build a request *plan* for a write operation — the dry-run preview.

This is the heart of the v0.2 safety model: before any write is executed, the CLI
resolves exactly what would go on the wire (method, URL, query, body) and shows it.
The function is **pure** — it takes an :class:`Operation` and the (coerced) keyword
arguments and returns a JSON-able dict. It performs no network or connection work,
so the dry-run path can never touch the target.

Two body conventions are handled:

* NSX names a single ``request_body_parameter`` (``is_body``) — the body is that
  parameter's value, unwrapped.
* vCenter leaves ``request_body_parameter`` unset and serializes every non-path,
  non-query parameter into the request body — so the body is the collection of
  those parameters.
"""

from __future__ import annotations

from typing import Any

from vsc.gen.model import Operation, Param
from vsc.output.render import jsonable


def _resolve_url(op: Operation, kwargs: dict[str, Any]) -> str:
    """Substitute ``{templateVar}`` placeholders using the path-var map."""
    url = op.url_template
    for field, template_var in op.path_var_map.items():
        if field in kwargs and kwargs[field] is not None:
            url = url.replace(f"{{{template_var}}}", str(kwargs[field]))
    return url


def _body(op: Operation, present: dict[str, Any]) -> Any:
    """Compute the request body from the present, coerced kwargs."""
    body_params = [p for p in op.params if p.is_body]
    if body_params:
        # NSX: a single named body parameter; the body is its value directly.
        name = body_params[0].name
        return jsonable(present[name]) if name in present else None
    # vCenter: every non-path, non-query parameter forms the body object.
    by_name: dict[str, Param] = {p.name: p for p in op.params}
    body = {
        name: jsonable(value)
        for name, value in present.items()
        if (p := by_name.get(name)) is not None and not p.in_path and not p.in_query
    }
    return body or None


def build_request_plan(op: Operation, sdk_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-able plan describing the wire request ``op`` would make.

    ``sdk_kwargs`` are the coerced keyword arguments (path/query/body values) that
    would be passed to the SDK method. ``None`` values are treated as absent.
    """
    present = {k: v for k, v in sdk_kwargs.items() if v is not None}
    by_name = {p.name: p for p in op.params}
    path_params = {
        name: jsonable(value) for name, value in present.items() if name in op.path_var_map
    }
    query = {
        name: jsonable(value)
        for name, value in present.items()
        if (p := by_name.get(name)) is not None and p.in_query
    }
    return {
        "method": op.http_method,
        "url": _resolve_url(op, present),
        "path_params": path_params,
        "query": query,
        "body": _body(op, present),
        "backend": op.backend,
        "service": op.service_short,
        "operation": op.cli_verb,
    }
