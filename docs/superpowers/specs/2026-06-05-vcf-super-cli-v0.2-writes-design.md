# vcf-super-cli (`vsc`) — v0.2 Writes Design

**Date:** 2026-06-05
**Status:** Approved
**Owner:** Thomas (github.com/thomaschristory)
**Milestone:** v0.2 — writes
**Builds on:** [v0.1 design](2026-06-05-vcf-super-cli-design.md) (read-only foundation, merged)

## Summary

v0.2 adds **write operations** (POST / PUT / PATCH / DELETE) to the dynamically
generated `vsc` command tree, with a **dry-run-by-default** safety model: every
write command previews the resolved request and changes **nothing** unless
`--apply` is passed. The preview is a stable, agent-friendly JSON envelope.

The v0.1 architecture was built forward-looking for this: `Operation`/`Param`
already carry `is_body`/`in_query`, `params.coerce_struct` already builds full
binding structs from JSON, `discover` already wires `request_body_parameter`, and
`ExitCode.CONFLICT` (7) / `ExitCode.UNAVAILABLE` (8) plus the vAPI `error_type`
map already exist. v0.2 therefore unlocks and exercises that machinery rather
than rebuilding it.

## Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Opt-in to writes | **Per-command `--apply` flag only** | Explicit, no hidden env/global state; read commands never show it. |
| Destructive confirmation | **`--apply` is the only gate** | No TTY prompt — fully scriptable / agent-friendly, never hangs on stdin. |
| Apply output | **Result + executed plan** | One stable envelope; agent sees exactly what was sent and what returned. |
| Write surface | **Unlock v0.1 catalog + expand** | Broader, useful write surface; expansion list is the milestone's scope dial. |

## Architecture

New module `vsc/gen/preview.py`; targeted changes to `gen/discover.py`,
`gen/model.py`, `gen/builder.py`, `output/render.py`, `cli/app.py`. No change to
the connect/config layers.

```
vsc/gen/
├── discover.py   # CHANGED: read_only=False path; catalog expansion; path_var_map
├── model.py      # CHANGED: Operation.is_write, Operation.path_var_map
├── preview.py    # NEW: build_request_plan(op, sdk_kwargs) -> plan dict (no network)
├── params.py     # UNCHANGED: coerce_struct already builds body structs
└── builder.py    # CHANGED: --apply injection; dry-run gate; write envelope
vsc/output/
└── render.py     # CHANGED: emit_request(plan, applied, result) write envelope
vsc/cli/app.py    # CHANGED: discover with read_only=False
```

### Write discovery & catalog (`discover.py`, `model.py`)

- `app.py` and `discover_all` call `discover_operations(..., read_only=False)`.
  The existing GET-only `continue` is the entire v0.1↔v0.2 switch.
- `Operation.is_write` property → `http_method != "GET"`. Drives `--apply`
  injection and envelope selection.
- `Operation.path_var_map: dict[str, str]` — field-name → URL template variable,
  captured from `rest.path_variables` at discovery time (verified against the
  installed SDK). Used by the plan builder to resolve `{placeholders}`.
- `_cli_verb`: confirm POST-action ops (`start`/`stop`/`reset`/`suspend`/`patch`)
  keep their own verb and never collapse to `get` (the `get` heuristics are
  gated on `http_method == "GET"` or read-name patterns; verify no write op_id
  trips the `"{" in low` / `read` branches).

**Catalog expansion** (all introspected offline; each added service also exposes
its reads, consistent with per-service discovery):

- **vSphere** (existing: VM, Host, Cluster, Datacenter, Datastore, Folder,
  Network) **+** `vm.power` (start/stop/reset/suspend), `vm.hardware`
  Cpu/Memory/Disk/Ethernet (PATCH writes), `ResourcePool`, and `vm.guest`
  identity where REST-backed.
- **NSX Policy** (existing: Segments, Tier0s, Tier1s, Services, Groups,
  SecurityPolicies, GatewayPolicies) **+** Tier1 interfaces, IP address pools,
  and DHCP server configs (PUT/PATCH/DELETE).

Services are imported defensively (existing `nsx_services` pattern): a moved or
absent symbol logs a warning and is skipped, never breaking the tree.

### Request-plan builder (`preview.py`)

`build_request_plan(op: Operation, sdk_kwargs: dict) -> dict` — a pure function
with **no Typer and no connection** dependency, testable standalone against
introspected ops:

```json
{
  "method": "POST",
  "url": "/api/vcenter/vm",
  "path_params": {},
  "query": {},
  "body": { "...": "user-supplied JSON, parsed" },
  "backend": "vsphere",
  "service": "vm",
  "operation": "create"
}
```

- `url`: `op.url_template` with `{var}` placeholders resolved via
  `op.path_var_map` from the (coerced) path-var values in `sdk_kwargs`.
- `body`: the **parsed JSON the user supplied** for the `is_body` param — faithful
  to what becomes the coerced struct and readable, avoiding vAPI-tagged
  `to_dict()` noise in the preview.
- `query`: values for params with `in_query` that are present.

### `--apply` gate & write envelope (`builder.py`, `render.py`)

- Write commands (`op.is_write`) get an injected `--apply/--no-apply` boolean
  option, default `False`. Read commands are unchanged (no `--apply`).
- Callback flow: coerce kwargs → `build_request_plan(...)`. Then:
  - **dry-run (default):** emit and exit 0, **without calling `connect_fn`**:
    ```json
    { "applied": false, "request": { ... },
      "apply_hint": "re-run with --apply to execute" }
    ```
    Invariant pinned by tests: dry-run performs no network/connection work.
  - **`--apply`:** connect → invoke → emit:
    ```json
    { "applied": true, "request": { ... }, "result": <rendered SDK response> }
    ```
- `render.emit_request(plan, applied, result)`: JSON (default) writes the
  envelope; `table` mode prints `METHOD url  (applied=…)` plus a result summary.
- Existing error handling (`envelope_for_vapi` / `envelope_for_transport`) wraps
  the apply invocation unchanged.

### Write-error coverage & body coercion

`ExitCode.CONFLICT`/`UNAVAILABLE` and the `ERROR_TYPE_TO_EXIT` map already exist.
v0.2 adds tests that exercise them through the write path:

- `ALREADY_EXISTS`, `ALREADY_IN_DESIRED_STATE`, `CONCURRENT_CHANGE`,
  `RESOURCE_IN_USE`, `NOT_ALLOWED_IN_CURRENT_STATE` → exit **7** (CONFLICT).
- `SERVICE_UNAVAILABLE`, `RESOURCE_BUSY`, `TIMED_OUT`,
  `UNABLE_TO_ALLOCATE_RESOURCE` → exit **8** (UNAVAILABLE).
- Body/struct roundtrip: a real write op's `--spec '{json}'` →
  `coerce_struct` → binding object, asserted field-by-field.

### Docs & bundled skill

- `skill/assets/SKILL.md`: dry-run-by-default, `--apply`, the write envelope
  shape, and write exit codes (7/8).
- New mkdocs "Writes" page; `mkdocs --strict` stays green.

## Testing

- **Discovery:** writes appear for expanded catalog; `--apply` present on write
  commands and absent on reads; verbs not collapsed to `get`.
- **Plan builder:** URL/path-var resolution, body passthrough, query extraction —
  no network.
- **Dry-run invariant:** a spy `connect_fn` is **never** called in dry-run; envelope
  shape asserted.
- **Apply path:** mocked service; `method(**kwargs)` invoked; `applied:true`
  envelope with `result`.
- **Coercion:** body/struct JSON → binding object roundtrip.
- **Errors:** CONFLICT/UNAVAILABLE mapping through the write path.
- `mypy --strict`, `ruff`, `mkdocs --strict`, CI all green.

## Issue breakdown (4 PRs, under Epic + v0.2 milestone)

1. **Discovery & catalog** — `read_only=False`, `Operation.is_write`,
   `path_var_map`, verb handling, catalog expansion.
2. **Dry-run engine** — `gen/preview.py` plan builder + `--apply` gate + write
   envelope in `builder`/`render` (the safety core).
3. **Write-error & coercion tests** — CONFLICT/UNAVAILABLE coverage + body/struct
   roundtrips.
4. **Docs & SKILL.md** — writes + the `--apply` safety model.

Each PR: `ruff` + `mypy --strict` + `pytest` + `mkdocs --strict` green, CI green,
and an adversarial (refute-before-accept) review before merge. No auto-merge; no
auto-run of e2e/PyPI workflows.

## Out of scope (v0.2)

Interactive confirmation prompts; env/global `--apply`; long-running task
polling/wait; NSX Manager + Global-Manager; SDDC Manager / Operations / LCM;
PyPI publishing (next roadmap item after v0.2); dynamic-value shell completion.
