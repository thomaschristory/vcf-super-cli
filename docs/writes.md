# Writes

`vsc` exposes the `vcf-sdk` write operations (`POST` / `PUT` / `PATCH` / `DELETE`)
as generated commands — `create`, `delete`, `set`, `patch`, power actions, and
more. Discover them with `--help`, e.g. `vsc vsphere vm --help` or
`vsc nsx segments --help`.

## Dry-run by default

**Every write previews the request and changes nothing unless you pass `--apply`.**
This is the core safety contract: a write command without `--apply` resolves the
request and prints it, but **never opens a connection** to vCenter or NSX.

```sh
vsc --profile prod vsphere vm delete vm-42            # DRY-RUN — prints the plan, changes nothing
vsc --profile prod vsphere vm delete vm-42 --apply    # executes the delete
```

There is no interactive prompt: `--apply` is the only gate, so the CLI stays fully
scriptable and never blocks on input.

## The request/response envelope

Both modes emit the same stable JSON envelope; branch on `applied`.

**Dry-run** (`stdout`, exit `0`):

```json
{
  "applied": false,
  "request": {
    "method": "DELETE",
    "url": "/vcenter/vm/vm-42",
    "path_params": { "vm": "vm-42" },
    "query": {},
    "body": null,
    "backend": "vsphere",
    "service": "vm",
    "operation": "delete"
  },
  "apply_hint": "re-run with --apply to execute"
}
```

**Applied** (`--apply`) carries the SDK response under `result` instead of
`apply_hint`:

```json
{
  "applied": true,
  "request": { "method": "DELETE", "url": "/vcenter/vm/vm-42", "...": "..." },
  "result": null
}
```

`request.url` is the resolved REST template (it may include a literal query string
the SDK bakes in, e.g. `?force=true`); `request.query` holds the structured query
parameters you supplied.

## Bodies and specs

Object bodies are passed as JSON to the relevant option and built into the SDK
struct. Some SDK calls name a single body parameter (NSX), others assemble the body
from the remaining parameters (vCenter `spec`):

```sh
# NSX: a named body parameter (--segment)
vsc --profile prod nsx segments set web --segment '{"display_name":"web"}'         # dry-run
vsc --profile prod nsx segments set web --segment '{"display_name":"web"}' --apply

# vCenter: a spec parameter (--spec)
vsc --profile prod vsphere vm create --spec '{"name":"vm-1", "...": "..."}' --apply
```

A malformed or incomplete body is reported as a structured usage error (exit `2`)
during the dry-run — before any connection — not as a traceback.

## Errors

Writes use the same [error envelope and exit codes](usage.md#exit-codes). The codes
most specific to writes are:

| Code | Name | Typical write cause |
|-----:|------|---------------------|
| 2 | USAGE | Malformed/incomplete body or arguments |
| 7 | CONFLICT | Already exists, in use, wrong state, concurrent change |
| 8 | UNAVAILABLE | Target busy, timed out, or temporarily unavailable |

## Examples

```sh
# Power a VM off — preview, then apply
vsc --profile prod vsphere power stop vm-42
vsc --profile prod vsphere power stop vm-42 --apply

# Create-or-replace an NSX Tier-1 (PUT upsert)
vsc --profile prod nsx tier1s set t1-web --tier1 '{"display_name":"web"}' --apply

# Delete a resource pool
vsc --profile prod vsphere resource-pool delete resgroup-9 --apply
```
