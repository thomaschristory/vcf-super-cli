# vcf-super-cli (`vsc`)

[![PyPI](https://img.shields.io/pypi/v/vcf-super-cli.svg)](https://pypi.org/project/vcf-super-cli/)
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
$ vsc nsx segments list --output table
$ vsc vsphere power stop vm-42 --apply        # writes are dry-run without --apply
```

> ⚠️ **Alpha / pre-release.** Reads (vSphere + NSX inventory) and writes are both
> available. **Writes are dry-run by default** — nothing changes without `--apply`,
> and a dry-run never opens a connection.

## Why

- **Mirrors the real API.** Commands come from the SDK's own vAPI metadata
  (`VapiInterface` services + `OperationRestMetadata`), covering both vCenter and
  NSX from one generator.
- **Modern.** REST-first via `vmware-vcenter`, with `pyVmomi` as a fallback where
  REST lacks coverage.
- **Safe by default.** Writes preview as dry-runs unless you pass `--apply`; a
  dry-run never opens a connection.
- **Agent-friendly.** Deterministic command shape, machine-readable JSON output,
  a stable error envelope with documented exit codes, and a bundled agent Skill.

## Scope

| Area | Status |
|------|--------|
| vSphere / vCenter read (`vsc vsphere …`) | ✅ v0.1 |
| NSX **Policy API** read (`vsc nsx …`) | ✅ v0.1 |
| Writes — dry-run by default + `--apply` (`vsc vsphere …` / `vsc nsx …`) | ✅ v0.2 |
| Ergonomics — offline shell completion, per-field filter flags + paging, pyVmomi fallback (`perf`/`events`/`tasks`/`inventory`) | ✅ v0.3 |
| Live resource-id completion | ✅ v0.4 |
| Find VMs by attribute — IP / hostname / MAC / guest OS / power (`vsc vsphere inventory find`) | ✅ v0.5 |
| NSX Manager / Global-Manager, SDDC Manager, Operations, LCM | deferred |

## Install

```sh
uv tool install vcf-super-cli      # recommended
# or
pipx install vcf-super-cli
# or
pip install vcf-super-cli
```

From source:

```sh
uv sync && uv run vsc --help
```

## Documentation

Full guide: **[thomaschristory.github.io/vcf-super-cli](https://thomaschristory.github.io/vcf-super-cli/)**

## License

Apache-2.0. See [LICENSE](LICENSE).
