# vcf-super-cli

A modern, agent-friendly CLI for **VMware Cloud Foundation 9** whose command tree
is **generated dynamically** from the official [`vcf-sdk`](https://pypi.org/project/vcf-sdk/)
vAPI bindings.

```console
$ vsc vsphere vm list --profile prod
$ vsc nsx segment list --output table
```

!!! warning "Alpha / pre-release"
    v0.1 is **read-only** (vSphere + NSX inventory). Writes arrive in v0.2 —
    dry-run by default, nothing changes without `--apply`.

## Highlights

- **Mirrors the real API** — commands come from the SDK's vAPI metadata, covering
  vCenter and NSX from one generator.
- **REST-first** via `vmware-vcenter`, `pyVmomi` fallback where needed.
- **Safe by default** — read-only now; future writes are dry-run unless `--apply`.
- **Agent-friendly** — JSON output, stable error envelope, documented exit codes,
  bundled agent Skill.

See the [Design](design.md) for how dynamic generation works.

## Install

```sh
uv tool install vcf-super-cli      # once published to PyPI
```

From source:

```sh
uv sync
uv run vsc --help
```
