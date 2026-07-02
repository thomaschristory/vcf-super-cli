# NSX Traceflow support

**Milestone:** v0.6 — NSX Traceflow · **Issue:** #58 · **Date:** 2026-07-02

## Problem

NSX Traceflow injects a synthetic packet at a source port and reports the exact
path it takes through the logical and physical topology — the first tool you reach
for when debugging "why can't A talk to B?". The `vcf-nsx` SDK ships the Policy
Traceflow services, but `vsc nsx` doesn't expose them: the NSX surface is a curated
allow-list (`_NSX_SERVICE_SPECS` in `vsc/gen/discover.py`) and Traceflow isn't on it.

## Approach

Pure allow-list addition. The generator already handles everything Traceflow needs —
dry-run writes with `--apply`, JSON struct bodies, path-var mapping, cursor paging —
so no generator changes are required. Add two Policy service classes to the catalog
and let discovery produce the commands.

## Surface

Two Policy services (Manager API stays deferred, out of scope):

| Service class | Module | Group |
|---|---|---|
| `Traceflows` | `vcf.nsx.policy.api.v1.infra_client` | `vsc nsx traceflows` |
| `Observations` | `vcf.nsx.policy.api.v1.infra.traceflows_client` | `vsc nsx observations` |

### `vsc nsx traceflows`

| Verb | HTTP | Notes |
|---|---|---|
| `list` | GET | list traceflow configs; gets `--all`/`--max-items`/`--limit` |
| `get <traceflow-id>` | GET | read one config |
| `set <traceflow-id> --traceflow-config '<json>'` | PUT | create/replace a config (start a trace) |
| `patch <traceflow-id> --traceflow-config '<json>'` | PATCH | partial update |
| `delete <traceflow-id>` | DELETE | remove a config |
| `policy-lm-restart-traceflow <traceflow-id>` | POST | restart action |

### `vsc nsx observations`

| Verb | HTTP | Notes |
|---|---|---|
| `list --traceflow-id <id>` | GET | the traced packet path (the actual result); paged |

## Behavior (inherited from existing infra — no new code)

- **Dry-run by default.** `set`/`patch`/`delete`/restart preview the resolved request
  and open no connection; `--apply` executes.
- **`--traceflow-config` is a STRUCT** → accepts a JSON blob, validated client-side
  before any connection. Malformed/incomplete JSON → clean usage error (exit 2).
- **Paging.** `traceflows list` and `observations list` get `--all` / `--max-items`
  / `--limit`.
- **Read contract holds.** Under `read_only=True` both services yield only `get`/`list`
  GETs, preserving the invariant asserted by `test_expanded_catalog_read_contract_holds`.

## Accepted quirks (deliberate — no special-casing)

- `observations` is its own top-level group, not nested under `traceflows`. This is
  how the generic generator names groups (by service short name); nesting would need
  a per-service override the generator doesn't have.
- The restart verb is the verbose `policy-lm-restart-traceflow` (POST with no
  `?action=`, so the op id is kebab-cased). Renaming is a separate cross-cutting
  concern, not part of this issue.

## Testing

Extend `tests/test_discover.py` (offline, against the real installed SDK):

1. `nsx_services()` includes `Traceflows` and `Observations`.
2. `traceflows` discovery yields `list`/`get`/`set`/`patch`/`delete` with the right
   HTTP methods, and `--traceflow-config` is a required STRUCT body on `set`.
3. `observations` discovery yields a `list` whose required `traceflow_id` is a path
   param.
4. The read-only contract still holds across the expanded catalog (existing test
   covers the new services automatically).

Builder-level (`tests/test_builder.py` style): `traceflows set` without `--apply`
emits a dry-run request plan and opens no connection.

## Docs

- README scope table: add a Traceflow row (or fold into NSX Policy).
- `docs/commands.md`: add `traceflows` / `observations` to the NSX table with a
  create→observe example.
- `vsc/skill/assets/SKILL.md`: add the two groups to the NSX group list.
- `CHANGELOG.md`: Added entry under Unreleased.

## Out of scope

- Manager API traceflow (`vcf.nsx.api.v1`).
- Group-nesting / verb-renaming ergonomics (separate issue if wanted).
