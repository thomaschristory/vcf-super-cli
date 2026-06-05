# vcf-super-cli (`vsc`)

[![CI](https://github.com/thomaschristory/vcf-super-cli/actions/workflows/test.yml/badge.svg)](https://github.com/thomaschristory/vcf-super-cli/actions/workflows/test.yml)
[![Lint](https://github.com/thomaschristory/vcf-super-cli/actions/workflows/lint.yml/badge.svg)](https://github.com/thomaschristory/vcf-super-cli/actions/workflows/lint.yml)
[![Docs](https://github.com/thomaschristory/vcf-super-cli/actions/workflows/docs.yml/badge.svg)](https://thomaschristory.github.io/vcf-super-cli/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

A modern, **agent-friendly** CLI for **VMware Cloud Foundation 9**. The command
tree is **generated dynamically** by introspecting the official
[`vcf-sdk`](https://pypi.org/project/vcf-sdk/) vAPI bindings — so the surface
mirrors the real VCF 9 API instead of being hand-maintained.

```console
$ vsc vsphere vm list --profile prod
$ vsc vsphere host get --host host-42
$ vsc nsx segment list --output table
```

> ⚠️ **Alpha / pre-release.** v0.1 is **read-only** (vSphere + NSX inventory).
> Writes arrive in v0.2 — **dry-run by default**, nothing changes without `--apply`.

## Why

- **Mirrors the real API.** Commands come from the SDK's own vAPI metadata
  (`VapiInterface` services + `OperationRestMetadata`), covering both vCenter and
  NSX from one generator.
- **Modern.** REST-first via `vmware-vcenter`, with `pyVmomi` as a fallback where
  REST lacks coverage.
- **Safe by default.** v0.1 is read-only; writes (v0.2) preview as dry-runs unless
  you pass `--apply`.
- **Agent-friendly.** Deterministic command shape, machine-readable JSON output,
  a stable error envelope with documented exit codes, and a bundled agent Skill.

## Scope

| Area | Status |
|------|--------|
| vSphere / vCenter read (`vsc vsphere …`) | v0.1 |
| NSX **Policy API** read (`vsc nsx …`) | v0.1 |
| Writes (dry-run + `--apply`) | v0.2 |
| NSX Manager / Global-Manager, SDDC Manager, Operations, LCM | deferred |

## Install

```sh
uv tool install vcf-super-cli      # (once published to PyPI)
# or, from source:
uv sync && uv run vsc --help
```

## Documentation

Full guide: **[thomaschristory.github.io/vcf-super-cli](https://thomaschristory.github.io/vcf-super-cli/)**

## License

Apache-2.0. See [LICENSE](LICENSE).
