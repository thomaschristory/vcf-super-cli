# vcf-super-cli (`vsc`) — Design

**Date:** 2026-06-05
**Status:** Approved (kickoff)
**Owner:** Thomas (github.com/thomaschristory)

## Summary

`vcf-super-cli` is a modern, agent-friendly CLI for **VMware Cloud Foundation 9**.
Its command tree is **generated dynamically** by introspecting the official PyPI
`vcf-sdk` vAPI bindings — the same philosophy as `netbox-super-cli`, but the
command surface is sourced from the **SDK's own embedded metadata** rather than a
live OpenAPI fetch. The result: one binary that mirrors the real VCF 9 API, splits
cleanly into `vsc vsphere …` and `vsc nsx …`, and is safe and scriptable by default.

Console scripts: `vcf-super-cli` and the short alias **`vsc`**.

## Why dynamic generation works here

Both `vmware-vcenter` and `vcf-nsx` are **vAPI stub libraries** built on the shared
`vmware-vapi-runtime`. Inspection of the 9.1.0.0 wheels confirms:

- Each service is a `VapiInterface` subclass (`VM`, `Host`, `Cluster`, `Datastore`,
  `Network`, `Datacenter`, `ResourcePool`, `Folder`, …).
- Every operation carries an `OperationRestMetadata` with `http_method`
  (`GET` / `POST` / `PUT` / `DELETE`), `path_variables`, and `query_parameters`.
- Parameters are typed via `StructType` / `StructDefinition` binding types.

So a single generator can walk these classes, read the REST metadata, and emit a
Typer command per operation. `http_method == "GET"` ⇒ a **read** command;
anything else ⇒ a **write** command (deferred to v0.2; dry-run by default + `--apply`).
Because the metadata is embedded in the installed SDK, the **tree builds offline** —
no server or credentials needed to render `--help`.

vCenter and NSX share the runtime, so **one generator covers both products.**

## Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Command model | Dynamic generation | User preference; SDK metadata makes it clean. |
| Generation source | **Static** SDK introspection | Deterministic, offline tree, version-pinned to the SDK. |
| vSphere interface | `vmware-vcenter` REST-first, `pyvmomi` fallback | Modern; drop to SOAP only where REST lacks coverage. |
| Top-level grouping | `vsc vsphere` / `vsc nsx` | Clean product split; hides `com.vmware` noise. |
| NSX surface (v0.1) | **Policy API only** | Current best practice; defer Manager + Global-Manager. |
| v0.1 scope | **Read-only** inventory | Nail auth/profiles/output/errors before any writes. |

## Architecture

```
vsc/
├── cli/
│   ├── app.py            # entrypoint: build Typer app, global options, main()
│   └── globals.py        # --profile, --output, --log-level, version callback
├── gen/
│   ├── discover.py       # find VapiInterface subclasses under configured namespaces
│   ├── operation.py      # model: Operation (name, verb, params, rest metadata)
│   ├── params.py         # map vAPI StructType -> Typer options/args + coercion
│   └── builder.py        # Operation -> typer.Command; assemble groups
├── connect/
│   ├── session.py        # vAPI Connector + auth (vCenter session, NSX)
│   └── targets.py        # vsphere vs nsx connection construction
├── config/
│   ├── profiles.py       # named profiles (platformdirs), env overrides, keyring opt
│   └── schema.py         # pydantic config models
├── output/
│   ├── render.py         # JSON (default) + Rich table; --output {json,table}
│   ├── errors.py         # stable error envelope
│   └── exit_codes.py     # documented exit codes (enum)
└── skill/
    ├── assets/SKILL.md   # bundled agent skill
    └── export.py         # `vsc skill export`
```

### Data flow (read command)

1. `vsc vsphere vm list --profile prod` → Typer command (generated).
2. Builder resolves the bound `Operation` (service `VM`, verb `list`, `GET`).
3. `connect.session` opens/reuses a vAPI connector for the profile's vCenter.
4. SDK call executed; result is a vAPI `VapiStruct`.
5. `output.render` converts to plain dict → JSON (default) or Rich table.
6. Exit code 0; errors → stable envelope + documented non-zero code.

### Command-tree generation

- A small **registry** maps top-level groups to SDK namespaces:
  - `vsphere` → `com.vmware.vcenter` (+ selected `com.vmware.esx`)
  - `nsx` → `vcf.nsx.policy`
- `discover.py` imports the namespace, finds `VapiInterface` subclasses, and for
  each, enumerates operations from the stub's REST metadata.
- v0.1 filters to `http_method == "GET"`.
- Sub-namespaces map to nested Typer groups (e.g. `vm hardware` → `vsc vsphere vm hardware`).
- Operation/param **names are normalized** (snake/kebab) with the raw name preserved
  for the wire call.

### Auth & profiles

- Named profiles in the platformdirs config dir; env-var overrides
  (`VSC_PROFILE`, `VSC_VCENTER_*`, `VSC_NSX_*`).
- vCenter: vAPI session auth (username/password → session id), OAuth2 path available.
- NSX: profile-scoped credentials.
- Secrets via OS keyring when available; documented plaintext fallback.
- `vsc init` / `vsc login` / `vsc profiles` management commands (curated, not generated).

### Output & safety contract

- **Default output: JSON** (stable shape). `--output table` for humans (Rich).
- **Error envelope:** `{ "error": {code, message, kind, details} }` on stderr.
- **Exit codes:** documented enum (0 ok, 1 generic, 2 usage, 3 auth, 4 not-found,
  5 connection, 6 config, …). Auto-rendered into docs.
- v0.1 is read-only. v0.2 introduces writes: **dry-run by default**, `--apply` required.

### Agent-friendliness

- Deterministic command shape; machine-readable JSON; stable errors + exit codes.
- Bundled `SKILL.md` shipped in the wheel (`force-include` `skills/vcf-super-cli`),
  exportable via `vsc skill export`.

## Testing

- `pytest` unit tests over `gen/` (introspection against the real installed SDK,
  no network), `params` coercion, `output` rendering, `config` profiles.
- vAPI calls mocked at the connector boundary.
- `tests/e2e/` (ignored by default) for live-server smoke tests, gated by env.
- `mypy --strict`, `ruff`, `pre-commit`.

## Roadmap / milestones

- **v0.1 — read-only foundation:** generator, vsphere+nsx read commands, auth/profiles,
  output contract, error envelope, exit codes, docs, CI, bundled skill.
- **v0.2 — writes:** POST/PUT/DELETE generation, dry-run by default + `--apply`.
- **v0.3 — ergonomics:** dynamic value completion, filters/pagination helpers,
  pyVmomi fallback commands for perf/inventory gaps.
- **later:** SDDC Manager / Operations / LCM namespaces; PyPI release; MCP sibling (TBD).

## Out of scope (v0.1)

Writes; NSX Manager + Global-Manager APIs; SDDC Manager / Operations / installer / LCM;
PyPI publishing (later); dynamic-value shell completion.
