"""Map SDK/transport exceptions to the stable error envelope + exit codes.

vAPI errors are both ``Exception`` and ``VapiStruct``; dispatch on the stable
``error_type`` string rather than ``isinstance`` chains. Transport-layer failures
(``requests`` connection/TLS errors) happen before the vAPI layer and are mapped
separately.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import com.vmware.vapi.std.errors_client as verr

from vsc.output.exit_codes import ExitCode

# vAPI ``error_type`` -> exit code. Unlisted/None -> ExitCode.ERROR.
ERROR_TYPE_TO_EXIT: dict[str, ExitCode] = {
    "UNAUTHENTICATED": ExitCode.AUTH,
    "UNAUTHORIZED": ExitCode.AUTH,
    "INVALID_ARGUMENT": ExitCode.USAGE,
    "UNSUPPORTED": ExitCode.USAGE,
    "UNEXPECTED_INPUT": ExitCode.USAGE,
    "OPERATION_NOT_FOUND": ExitCode.USAGE,
    "NOT_FOUND": ExitCode.NOT_FOUND,
    "RESOURCE_INACCESSIBLE": ExitCode.NOT_FOUND,
    "ALREADY_EXISTS": ExitCode.CONFLICT,
    "ALREADY_IN_DESIRED_STATE": ExitCode.CONFLICT,
    "RESOURCE_IN_USE": ExitCode.CONFLICT,
    "FEATURE_IN_USE": ExitCode.CONFLICT,
    "NOT_ALLOWED_IN_CURRENT_STATE": ExitCode.CONFLICT,
    "CONCURRENT_CHANGE": ExitCode.CONFLICT,
    "SERVICE_UNAVAILABLE": ExitCode.UNAVAILABLE,
    "RESOURCE_BUSY": ExitCode.UNAVAILABLE,
    "TIMED_OUT": ExitCode.UNAVAILABLE,
    "UNABLE_TO_ALLOCATE_RESOURCE": ExitCode.UNAVAILABLE,
    "INTERNAL_SERVER_ERROR": ExitCode.ERROR,
    "CANCELED": ExitCode.ERROR,
}


def _messages(err: Any) -> str:
    msgs = getattr(err, "messages", None) or []
    texts = [getattr(m, "default_message", None) for m in msgs]
    joined = "; ".join(t for t in texts if t)
    return joined or str(err) or err.__class__.__name__


def envelope_for_vapi(err: Any) -> tuple[dict[str, Any], ExitCode]:
    """Build the error envelope + exit code for a vAPI error."""
    error_type = getattr(err, "error_type", None)
    code = ERROR_TYPE_TO_EXIT.get(error_type or "", ExitCode.ERROR)
    detail: Any
    try:
        detail = err.to_dict()
    except Exception:
        detail = None
    env = {
        "error": {
            "code": int(code),
            "kind": error_type or err.__class__.__name__,
            "message": _messages(err),
            "details": detail,
        }
    }
    return env, code


def envelope_for_transport(err: Exception) -> tuple[dict[str, Any], ExitCode]:
    """Build the error envelope + exit code for a transport-layer error."""
    name = err.__class__.__name__
    code = ExitCode.AUTH if "SSL" in name else ExitCode.CONNECTION
    env = {
        "error": {
            "code": int(code),
            "kind": name,
            "message": str(err) or name,
            "details": None,
        }
    }
    return env, code


def render_error(env: dict[str, Any], fmt: str) -> None:
    """Print the error envelope to stderr (JSON always; ``message`` for tables)."""
    if fmt == "table":
        print(env["error"]["message"], file=sys.stderr)
    else:
        print(json.dumps(env, default=str), file=sys.stderr)


def is_vapi_error(err: BaseException) -> bool:
    """True if ``err`` is a vAPI ``Error`` (has the stable ``error_type``)."""
    return isinstance(err, verr.Error)
