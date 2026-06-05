# vcf-super-cli v0.3 — Ergonomics (design)

**Status:** approved 2026-06-05. Milestone: `v0.3 — ergonomics` (#3).
**Predecessors:** [v0.1 design](2026-06-05-vcf-super-cli-design.md), [v0.2 writes design](2026-06-05-vcf-super-cli-v0.2-writes-design.md).

## Goal

Make the dynamically-generated CLI pleasant to drive by hand and still trivially
scriptable by an agent. Three independent feature areas, each shipped as its own
issue/PR under milestone #3:

1. **Static shell completion** — offline tab-completion of enums, output formats,
   profile names, and per-field filter choices.
2. **Filter & pagination helpers** — per-field filter flags (augmenting today's
   `--filter '<json>'` blob) and friendlier paging (`--all`, `--max-items`,
   `--limit`).
3. **pyVmomi fallback commands** — hand-written read commands (perf, events/tasks,
   inventory walk) for gaps the vAPI/REST surface doesn't cover.

The agent contract is unchanged and non-negotiable: stable JSON output, the
documented error envelope, the frozen exit codes, and **writes stay dry-run by
default**. The pyVmomi additions are all reads, so they need no `--apply` gate.

## Locked decisions (from brainstorm, 2026-06-05)

- **Completion is static/offline only.** No feature in v0.3 hits the API during
  `<TAB>`. Live resource-ID completion (e.g. completing `<vm>` from a live list)
  is explicitly **deferred to v0.4**; the param model already carries
  `resource_types` so it remains a clean future extension.
- **Filter flags augment, never replace, `--filter`.** Raw `--filter '<json>'`
  stays as the base layer / escape hatch; generated per-field flags merge over it.
- **Pagination:** `--all` auto-follows the NSX cursor; `--max-items` caps total;
  `--limit` is a client-side cap for non-cursor (vSphere) lists. NSX
  `--page-size`/`--cursor` already exist as generated query options.
- **pyVmomi covers all three families** (perf, events/tasks, inventory walk),
  built on a small shared `SmartConnect` foundation.

---

## Feature 1 — Static shell completion

### Behaviour

Completion values are derived entirely from the introspected `Param` model plus
local config — never from a network call. `--help` and completion both stay fully
offline.

Completed surfaces:

| Surface | Source | Example |
|---------|--------|---------|
| enum option | `param.enum_values` | `--power-state POWERED_<TAB>` → `POWERED_ON`, `POWERED_OFF` |
| `--output` / `-o` | `OutputFormat` members | `-o <TAB>` → `json`, `table` |
| global `--profile` / `-p` | profile names from `load_config()` (offline file read) | `-p <TAB>` → `prod`, `lab` |
| per-field filter enum flags | reuse enum completer (feature 2) | `--filter-power-state <TAB>` |

Resource-ID args (the `<vm>` positionals) are **not** completed in v0.3.

### Implementation

- New module **`vsc/gen/complete.py`** — pure completer factories:
  - `enum_completer(values: list[str]) -> Callable[[str], list[str]]`
  - `profile_completer() -> Callable[[str], list[str]]`
  Each takes the Click `incomplete` string and returns the prefix-filtered
  candidate list. No `ctx`/`param` dependency → unit-testable without a shell.
- **`vsc/gen/builder.py`** `_build_signature`: when a non-path option is built for
  an `ENUM` param, pass `autocompletion=enum_completer(param.enum_values)` to
  `typer.Option`. When building `--output`, attach an `OutputFormat` completer.
- **`vsc/cli/app.py`** main callback: attach `profile_completer()` to `--profile`.
- Root app already sets `add_completion=True`; document `vsc --install-completion`
  and `vsc --show-completion` in `docs/usage.md`.

### Tests

`tests/test_complete.py` — completer factories return correctly prefix-filtered
lists, empty `incomplete` returns all, no match returns `[]`. A smoke test asserts
generated enum options carry an `autocompletion` callback.

---

## Feature 2 — Filter & pagination helpers

### Per-field filter flags

vCenter list operations take a single `filter` parameter that is a `STRUCT`
(`VM.FilterSpec` etc.). Today the user must pass it as `--filter '<json>'`. v0.3
additionally flattens that struct's fields into typed options.

- **Detection:** on a read/list op, a parameter that is `ParamKind.STRUCT` **and
  named `filter`** is flattened. Write-body structs are *not* flattened — they
  stay JSON (`--spec`, `--segment`, …).
- **Generated flags:** each struct field → `--<field>` (kebab-cased). `list`/`set`
  fields are **repeatable** (`list[str]` annotation, multiple uses accumulate).
  `enum` fields carry choices in help + the enum completer.
- **Precedence / merge:** raw `--filter '<json>'` provides the base dict; per-field
  flags merge **over** it (a flag wins over the same key in the blob). The merged
  dict is coerced into the FilterSpec via the existing
  `coerce_struct`/`coerce_value` path — no new coercion logic.
- **Collisions:** a flattened field whose flag would collide with a reserved option
  (`--output`, `--apply`) or another option is suffixed using the existing
  `_sig_name` mechanism.

New helper **`vsc/gen/filters.py`**:
- `flatten_filter(param: Param) -> list[Param]` — child params for each struct field
  (built with `param_from_type` on `struct_type.get_field(name)`).
- `assemble_filter(base_json, field_values, param) -> Any` — merge base + per-field
  values and coerce into the struct. Pure; unit-testable.

`builder.py` consumes these: `_build_signature` emits the child options (tracking
them so `_collect_kwargs` knows to reassemble rather than pass them through), and
`_collect_kwargs` calls `assemble_filter` to rebuild the single `filter` kwarg.

### Pagination

NSX Policy list ops return a `*ListResult` struct (`.results`, `.cursor`,
`.result_count`) and already expose `cursor`/`page_size` as generated query
options. vSphere REST list ops return a plain list and do not paginate.

Injected options on **list verbs** (`op.cli_verb == "list"`):

| Flag | Applies to | Effect |
|------|-----------|--------|
| `--all` | cursor lists (NSX) | follow `.cursor` across pages, concatenate `.results`, stop at `--max-items` |
| `--max-items N` | all lists | hard cap on returned items (post-fetch for vSphere, loop-stop for `--all`) |
| `--limit N` | non-cursor lists (vSphere) | client-side slice of the returned list |

Without `--all`, a cursor list returns one page **including** its `cursor`, so an
agent can paginate manually. `--all` and `--max-items` interact: the follow loop
stops once `--max-items` items are collected.

New helper **`vsc/gen/paginate.py`**:
- `follow_cursor(fetch_page, *, max_items) -> list` — `fetch_page(cursor) ->
  (results, next_cursor)`; loops until `next_cursor` is empty/repeated or the cap
  is hit. Pure given the `fetch_page` callable (the callable closes over the SDK
  method in `builder.py`); unit-testable with a fake pager.

`builder.py` `make_command` detects a cursor-bearing result and, when `--all` is
set, drives `follow_cursor`; otherwise applies `--limit`/`--max-items` slicing
before `emit()`.

### Tests

`tests/test_filters.py` — flatten produces one child per field with correct
kind/required/repeatable; assemble merges blob + flags with flags winning; enum
field carries choices. `tests/test_paginate.py` — `follow_cursor` concatenates,
respects `max_items`, terminates on empty/duplicate cursor. Builder integration
tests assert a vCenter list op grows `--<field>` options and an NSX list op grows
`--all`/`--max-items`.

---

## Feature 3 — pyVmomi fallback commands

Hand-written read commands for gaps the vAPI/REST surface doesn't cover, mounted
into the existing `vsc vsphere` tree and emitted through the existing
`emit()`/error-envelope contract.

### Foundation

- New module **`vsc/connect/vmomi.py`**:
  - `connect_vmomi() -> ServiceInstance` via `pyVim.connect.SmartConnect`, reusing
    `resolve_target("vsphere")` for server/user/password and an `ssl` context that
    honours `verify` (unverified context when `insecure`). Cached like the vAPI
    connections (`reset_cache()` clears it); `Disconnect` registered at process
    exit.
  - `vmomi_jsonable(obj) -> Any` — convert managed-object / data-object trees into
    plain JSON-able dicts (`moref` → `{"type", "value"}`, data objects → field
    dicts, leave scalars/datetimes alone) so `emit()` renders them like any other
    result.
- New package **`vsc/pyvmomi/`**, one module per family, each exposing a
  `typer.Typer`. `vsc/cli/app.py` adds them onto the vsphere group
  (`vsphere_group.add_typer(perf_app, name="perf")`, …). pyVmomi errors
  (`vim.fault.*`, connection failures) map into the existing envelope/exit codes
  (auth→3, not-found→4, connection→5) via a small adapter reusing
  `vsc/output/errors.py` patterns.

### Commands

- **`vsc vsphere perf`** — real-time/historical counters via `PerformanceManager`.
  e.g. `perf vm <vm> --metric cpu.usage [--interval 20s]`,
  `perf host <host> --metric mem.usage`. Resolves the counter id, queries
  `QueryPerf`, emits timestamped samples.
- **`vsc vsphere events`** — recent events via `EventManager` with `--since`/entity
  filters. **`vsc vsphere tasks`** — running + recent tasks via `TaskManager`.
- **`vsc vsphere inventory`** — `PropertyCollector` walk for properties the REST
  list ops omit (device tree, custom attributes, relationships), e.g.
  `inventory vm <vm> --props config.hardware`.

All are reads → no `--apply`. They accept the same `--output json|table` and obey
`--profile`.

### Tests

pyVmomi has no offline-introspection trick like the vAPI bindings, so tests mock
`SmartConnect`/`ServiceInstance` and the relevant managers. `tests/test_vmomi.py`
covers `vmomi_jsonable` conversion (moref/data-object/scalar) purely;
`tests/test_pyvmomi_*.py` drive each command against a fake `ServiceInstance`
asserting the emitted JSON shape and error mapping. No live vCenter required.

---

## Cross-cutting

- Each feature PR updates the relevant `docs/` page(s) and the bundled
  `vsc/skill/assets/SKILL.md` for any new surface.
- `ruff`, `mypy --strict`, `pytest`, and `mkdocs --strict` stay green; CI green
  before merge.
- Every PR gets an adversarial **refute-before-accept** review pass; findings are
  fixed before merge.

## Issues (milestone #3)

| Issue | Title | Depends on |
|-------|-------|-----------|
| Epic | v0.3 — ergonomics | — |
| A | Static shell completion (enums, `--output`, `--profile`, filter choices) | — |
| B | Filter & pagination helpers (per-field flags + `--all`/`--max-items`/`--limit`) | — |
| C | pyVmomi fallback foundation + `vsc vsphere perf` | — |
| D | pyVmomi events & tasks | C |
| E | pyVmomi inventory walk | C |
| F | v0.3 docs/SKILL roundup + release prep | A–E |

Build order: A and B in parallel; C → (D, E); F last. The release tag (`vX.Y.Z`)
is pushed **manually by the maintainer** after F merges — `release.yml` keeps **no
`environment:` block** (the PyPI trusted publisher is registered with a blank
environment; they must stay matched).

## Out of scope (v0.3)

- Live resource-ID completion (hits the API) — v0.4 candidate.
- pyVmomi *writes* — the fallback surface is read-only this milestone.
- NSX Manager / Global-Manager APIs (still Policy-only).
