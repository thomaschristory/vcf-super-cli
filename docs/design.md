# Design

`vsc` builds its command tree by **statically introspecting the installed
`vcf-sdk` vAPI bindings**. Both `vmware-vcenter` and `vcf-nsx` are vAPI stub
libraries on the shared `vmware-vapi-runtime`:

- Each service is a `VapiInterface` subclass (`VM`, `Host`, `Cluster`,
  `Datastore`, `Network`, …).
- Every operation carries `OperationRestMetadata` (`http_method`,
  `path_variables`, `query_parameters`).
- Parameters are typed via `StructType` binding types.

A single generator walks those classes and emits one Typer command per
operation. `http_method == "GET"` ⇒ a read command; other verbs ⇒ writes
(dry-run by default + `--apply`). Because the metadata ships inside the SDK, the
tree builds **offline** — no server needed to render `--help`.

Top-level grouping:

- `vsc vsphere …` → `com.vmware.vcenter` (+ selected `com.vmware.esx`)
- `vsc nsx …` → `vcf.nsx.policy` (NSX Policy API)

The introspected intermediate representation is a list of `Operation` objects,
each carrying typed `Param`s (`vsc/gen/model.py`). Everything below is built from
that one model.

## Ergonomics (v0.3)

These build on the introspected `Param` model without changing the agent
contract.

### Offline shell completion

Completion values come entirely from the model and local config — **never a
network call**, so `<TAB>` stays fast and `--help` stays offline. Enum options
complete from their fixed choices, `--output` from the output formats, and
`--profile` from configured profile names (`vsc/gen/complete.py`). Completing a
live resource id would require a connection and is deferred to a later release.

### Per-field filter flags

A `list` operation takes a single `filter` parameter that is a struct
(`VM.FilterSpec` etc.). The generator flattens that struct into typed
`--<field>` options (repeatable for list/set fields; enum fields validate and
complete their choices). The raw `--filter '<json>'` blob remains as a base
layer that per-field flags merge **over** (`vsc/gen/filters.py`).

### Pagination

`list` commands gain `--all` (follow the NSX cursor across pages), `--max-items`
(cap the total), and `--limit` (client-side cap for non-paginated vSphere
lists). Without `--all`, a paginated list returns one page and surfaces its
`cursor` for manual paging; on non-cursor backends `--all` is a no-op and the
output stays a plain array (`vsc/gen/paginate.py`).

## pyVmomi fallback (v0.3)

A few inventory/performance areas are only reachable through the older pyVmomi
SOAP API. Those are **hand-written read-only commands** mounted under
`vsc vsphere` alongside the generated ones, sharing the same output contract:

- a separate connection path, `connect_vmomi()` via `SmartConnect`, reusing the
  resolved vSphere credentials and honouring `--insecure` like the REST path
  (`vsc/connect/vmomi.py`);
- `vmomi_jsonable()` collapses managed objects to their moref and data objects to
  dicts so results render like any other;
- a shared `run_read()` runner maps pyVmomi faults onto the same error envelope
  and exit codes (`vsc/pyvmomi/runner.py`).

Commands: `perf` (PerformanceManager counters), `events` / `tasks`
(Event/Task managers), and `inventory` (a PropertyCollector property walk). All
are reads — no `--apply`.

## Design specs

The authoritative, milestone-by-milestone designs live in the repository:

- [v0.1 — dynamic read-only CLI](https://github.com/thomaschristory/vcf-super-cli/blob/main/docs/superpowers/specs/2026-06-05-vcf-super-cli-design.md)
- [v0.2 — writes](https://github.com/thomaschristory/vcf-super-cli/blob/main/docs/superpowers/specs/2026-06-05-vcf-super-cli-v0.2-writes-design.md)
- [v0.3 — ergonomics](https://github.com/thomaschristory/vcf-super-cli/blob/main/docs/superpowers/specs/2026-06-05-vcf-super-cli-v0.3-ergonomics-design.md)

## Contracts

- **Output:** JSON by default; `--output table` for humans.
- **Errors:** stable envelope `{ "error": { code, message, kind, details } }`.
- **Exit codes:** documented `IntEnum` (`0` ok, `1` generic, `2` usage, `3` auth,
  `4` not-found, `5` connection, `6` config, `7` conflict, `8` unavailable).
- **Writes:** dry-run by default; `--apply` is the only gate and a dry-run opens
  no connection.
