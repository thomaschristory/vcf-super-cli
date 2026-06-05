"""Introspected command model: :class:`Operation` and :class:`Param`.

These dataclasses are the generator's intermediate representation. ``discover``
populates them from the SDK's vAPI metadata; ``params`` and ``builder`` consume
them. They carry only plain Python data plus opaque references to the original
vAPI type objects (``raw_type``) and binding classes (``struct_class``) needed at
invocation time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParamKind(str, Enum):
    """The unwrapped, concrete kind of a parameter's vAPI type."""

    STRING = "string"
    INTEGER = "integer"
    DOUBLE = "double"
    BOOLEAN = "boolean"
    ENUM = "enum"
    ID = "id"
    SECRET = "secret"
    DATETIME = "datetime"
    URI = "uri"
    LIST = "list"
    SET = "set"
    MAP = "map"
    STRUCT = "struct"
    DYNAMIC = "dynamic"
    BLOB = "blob"


# Scalar kinds that map to a single CLI value (no JSON / container handling).
SCALAR_KINDS: frozenset[ParamKind] = frozenset(
    {
        ParamKind.STRING,
        ParamKind.INTEGER,
        ParamKind.DOUBLE,
        ParamKind.BOOLEAN,
        ParamKind.ENUM,
        ParamKind.ID,
        ParamKind.SECRET,
        ParamKind.DATETIME,
        ParamKind.URI,
    }
)


@dataclass
class Param:
    """A single operation parameter, unwrapped from its vAPI ``Type``."""

    name: str
    kind: ParamKind
    required: bool
    in_path: bool = False
    in_query: bool = False
    is_body: bool = False
    resource_types: str | None = None
    enum_values: list[str] = field(default_factory=list)
    element: Param | None = None
    key_kind: ParamKind | None = None
    value_kind: ParamKind | None = None
    struct_name: str | None = None
    struct_class: type | None = None
    raw_type: Any = None


@dataclass
class Operation:
    """A single introspected, invokable operation on a service class."""

    backend: str  # 'vsphere' | 'nsx'
    service_cls: type
    iface_id: str
    op_id: str
    method_name: str
    cli_verb: str
    http_method: str
    url_template: str
    path_vars: list[str] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    output_type: Any = None
    error_types: list[Any] = field(default_factory=list)

    @property
    def service_short(self) -> str:
        """The last segment of the vAPI interface id, e.g. ``VM`` -> ``vm``."""
        return self.iface_id.split(".")[-1].lower()
