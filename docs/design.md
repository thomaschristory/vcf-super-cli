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
(v0.2, dry-run by default + `--apply`). Because the metadata ships inside the
SDK, the tree builds **offline** — no server needed to render `--help`.

Top-level grouping:

- `vsc vsphere …` → `com.vmware.vcenter` (+ selected `com.vmware.esx`)
- `vsc nsx …` → `vcf.nsx.policy` (NSX Policy API)

The full, authoritative design lives in the repository at
[`docs/superpowers/specs/2026-06-05-vcf-super-cli-design.md`](https://github.com/thomaschristory/vcf-super-cli/blob/main/docs/superpowers/specs/2026-06-05-vcf-super-cli-design.md).

## Contracts

- **Output:** JSON by default; `--output table` for humans.
- **Errors:** stable envelope `{ "error": { code, message, kind, details } }`.
- **Exit codes:** documented `IntEnum` (`0` ok, `2` usage, `3` auth, `4`
  not-found, `5` connection, `6` config, `1` generic).
