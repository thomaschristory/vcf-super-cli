# Changelog

All notable changes to `vcf-super-cli` are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/), and from v1.0.0 the project
will follow [Semantic Versioning](https://semver.org/). While on `0.x`, minor
versions may include breaking changes.

## [Unreleased]

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
