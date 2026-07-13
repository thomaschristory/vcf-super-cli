# Changelog

All notable changes to `vcf-super-cli` are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/), and from v1.0.0 the project
will follow [Semantic Versioning](https://semver.org/). While on `0.x`, minor
versions may include breaking changes.

## [Unreleased]

### Security

- **CI supply-chain & repo hardening** (#57) — closes the security-audit findings.
  All GitHub Actions across the five workflows are now pinned to immutable 40-char
  commit SHAs (with trailing version comments), including the PyPI trusted-publishing
  step in `release.yml` which previously used the `release/v1` branch ref (F1/F2). A
  new `.github/dependabot.yml` keeps those SHAs and the Python deps current, and
  Dependabot alerts/security updates plus branch protection on `main` are enabled at
  the repo level (F4/F5). `docs.yml` now grants `pages: write`/`id-token: write` only
  on the `deploy` job instead of workflow-wide (F6).
- **Insecure-TLS hardening** (#57) — when a connection actually runs with TLS
  verification disabled (`insecure` / `VSC_<BACKEND>_INSECURE`), `vsc` now logs an
  `insecure_tls` warning to stderr (F3). Added optional CA-bundle pinning via
  `ca_bundle` in a profile or `VSC_<BACKEND>_CACERT`, so self-signed lab certs can be
  verified instead of disabling verification entirely. The resolved `server` value is
  now validated as a bare host/host:port, rejecting a scheme, path, query, or `@`
  userinfo that could redirect the authenticated session (F7).

## v0.6.0 — 2026-07-03

NSX Traceflow — inject a synthetic packet and read the exact path it takes through
the topology, the first tool for "why can't A reach B?".

### Added

- **`vsc nsx traceflows` / `vsc nsx observations`** (#58) — NSX Policy Traceflow.
  Inject a synthetic packet and read the exact path it takes through the topology —
  the first tool for "why can't A reach B?". `traceflows` exposes the config surface
  (`list`/`get`/`set`/`patch`/`delete` + the `policy-lm-restart-traceflow` action);
  `set <id> --traceflow-config '<json>'` starts a trace (dry-run by default, `--apply`
  to execute). `observations list <traceflow-id>` returns the traced path.
  Pure allow-list addition — no generator changes; writes, JSON struct bodies and
  paging come from the existing machinery. Manager API traceflow stays deferred.

### Fixed

- `list --all` no longer crashes on operations that return a cursor-shaped result
  but take no `cursor` input parameter (e.g. `nsx observations list`). Cursor
  following is now guarded by whether the op actually accepts a `cursor`; for those
  that don't, `--all` degrades to a safe single-page no-op instead of re-invoking
  with a rejected `cursor` kwarg.

## v0.5.0 — 2026-06-08

Find VMs by attribute. Answers the everyday *"which VM has `10.20.3.41`?"* — a
reverse lookup the REST `vm list` filter can't do, because guest networking lives
only on the pyVmomi `guest.*` properties.

### Added

- **`vsc vsphere inventory find`** (#54) — locate VMs by guest/runtime attribute
  without knowing the moid: `--ip` (exact or CIDR, IPv4/IPv6, across the primary and
  every NIC address), `--name`, `--hostname`, `--guest-os` (case-insensitive
  substring or glob), `--mac` (exact), and `--power-state`. Flags **AND** together; a
  repeated flag **ORs** within its field; at least one match flag is required (it
  refuses to dump the whole inventory). `--props` (repeatable) widens each hit's
  output only — never a match criterion. One PropertyCollector round-trip over a
  container view (always destroyed); a pure, pyVmomi-free matcher does the filtering.
  Reads only — no `--apply` — and emits the same JSON / error envelope / exit codes
  as the other pyVmomi fallback commands.

## v0.4.0 — 2026-06-08

Live resource-id completion. Pressing `<TAB>` on an id-typed argument can now
suggest **real ids** from the live inventory — strictly opt-in, cached, and
fail-soft. The agent-facing contract is unchanged: stable JSON, error envelope,
exit codes, dry-run-by-default writes, and `--help` stays fully offline.

### Added

- **Live resource-id completion** (#44), opt-in via `VSC_COMPLETE_DYNAMIC=1` and
  off by default. When enabled, `<TAB>` on an id arg/option suggests live ids for
  the resource type (VMs, hosts, clusters, datacenters, datastores, resource
  pools), with each resource's name shown as completion help. Built on:
  - a resource-type → list-op **registry** derived purely by introspecting the
    SDK metadata (#45), no network;
  - a **TTL cache** under the platform cache dir, keyed by
    profile/backend/resource-type (default 60s, `VSC_COMPLETE_TTL` override) (#46);
  - a **dynamic completer** whose fetch is time-bounded (`VSC_COMPLETE_TIMEOUT`,
    default 2s) and blanket fail-soft — any error, missing auth, or timeout
    yields no suggestions and is never cached (#47).
- Static/offline completion (enums, output formats, profiles, filter enums) is
  unchanged and remains the default. `--help` and command execution never open a
  connection for completion.

### Notes

- Live completion is a human convenience only; agents should keep using `list`
  to discover ids and must not depend on completion for correctness (#48).

## v0.3.0 — 2026-06-05

Ergonomics: friendlier filtering and paging, offline shell completion, and a
pyVmomi fallback surface for gaps the REST/vAPI layer doesn't cover. The
agent-facing contract is unchanged — stable JSON, error envelope, exit codes,
and writes still dry-run by default.

### Added

- **Static shell completion** (#32), fully offline — never opens a connection.
  Completes enum option choices, output formats, configured profile names, and
  `list` filter enum values. Install with `vsc --install-completion`. (Live
  resource-id completion is intentionally deferred to a later release.)
- **Per-field filter flags** (#33). `list` commands flatten the SDK filter spec
  into typed `--<field>` options (repeatable for list/set fields; enum choices
  validated and completed), e.g. `vsc vsphere vm list --power-states POWERED_ON
  --names web-1`. The raw `--filter '<json>'` blob stays as a base layer that
  per-field flags override.
- **Pagination helpers** (#33): `--all` follows the NSX cursor across pages;
  `--max-items N` caps the total; `--limit N` is a client-side cap for
  non-paginated (vSphere) lists. Without `--all`, a paginated `list` returns one
  page and surfaces its `cursor` for manual paging.
- **pyVmomi fallback commands** (read-only) under `vsc vsphere`, for areas the
  REST/vAPI surface lacks — same JSON / error-envelope / exit-code contract:
  - `perf vm|host --metric <group.name>` — performance counters via the
    PerformanceManager (#34).
  - `events list [--vm|--host] [--since 1h]` and `tasks list` — recent events
    and recent/running tasks (#35).
  - `inventory vm|host [--props <path>]…` — a PropertyCollector property walk
    (#36).

### Changed

- Documentation and the bundled agent `SKILL.md` describe completion, the filter
  and paging flags, and the pyVmomi fallback surface.

## v0.2.0 — 2026-06-05

First PyPI release. Adds the **write** surface on top of the v0.1 read-only
foundation, with a dry-run-by-default safety model.

### Added

- **Write operations** (`POST`/`PUT`/`PATCH`/`DELETE`) are generated from the
  `vcf-sdk` vAPI metadata alongside reads (#20). Clean, collision-free verbs:
  `POST ?action=X` → `X`; otherwise `PUT` → `set`, `PATCH` → `patch`,
  `DELETE` → `delete` (force variants prefixed `force-`); `POST` without an
  action keeps its operation id.
- **Dry-run by default + `--apply`** (#21). Every write previews the resolved
  request and changes nothing — and opens **no connection** — unless `--apply`
  is passed. `--apply` is the only gate (no interactive prompt), so the CLI
  stays fully scriptable. New `vsc/gen/preview.py` builds the request plan.
- **Stable write envelope**, identical across modes — branch on `applied`:
  - dry-run: `{ "applied": false, "request": { method, url, path_params, query, body, … }, "apply_hint": … }`
  - applied: `{ "applied": true, "request": { … }, "result": <sdk response> }`
- **Body/spec construction from JSON** for both conventions: NSX's named request
  body and vCenter's spec parameters, built into the SDK binding structs.
- **Catalog expansion**: vSphere `resource-pool` and the VM power/hardware leaves
  (`power`, `cpu`, `memory`, `disk`, `ethernet`); NSX `ip-pools`,
  `dhcp-server-configs`, `dhcp-relay-configs`, and Tier-1 `locale-services`.
- **`CONFLICT` (7) / `UNAVAILABLE` (8)** exit-code coverage for write errors
  (#22), derived from the error-type map so it can't drift.

### Changed

- A malformed or incomplete write body is reported during the dry-run as the
  structured usage envelope (exit `2`) — before any connection — not as a
  traceback.
- Documentation and the bundled agent `SKILL.md` describe the write surface and
  the `--apply` safety model (#23).

## v0.1.0 — 2026-06-05

Initial read-only foundation (not published to PyPI).

### Added

- Command tree **generated dynamically** by introspecting the installed `vcf-sdk`
  vAPI bindings (`VapiInterface` services + `OperationRestMetadata`), fully
  offline — `--help` works without a server or credentials.
- Read (`GET`) commands for vSphere/vCenter (`vsc vsphere …`) and NSX Policy
  (`vsc nsx …`), split into two product groups.
- Named **profiles** with env-var overrides and optional OS-keyring secret
  storage; `--profile/-p` selection.
- **Output contract**: JSON by default, `--output table` for humans; a stable
  error envelope on stderr and documented, frozen **exit codes**.
- Bundled agent **Skill** shipped in the wheel, exportable via `vsc skill export`.
