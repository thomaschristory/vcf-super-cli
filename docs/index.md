# vcf-super-cli

A modern, agent-friendly CLI for **VMware Cloud Foundation 9** whose command tree
is **generated dynamically** from the official [`vcf-sdk`](https://pypi.org/project/vcf-sdk/)
vAPI bindings.

```console
$ vsc vsphere vm list --power-states POWERED_ON --profile prod
$ vsc nsx segments list --all --output table
$ vsc vsphere perf vm vm-42 --metric cpu.usage
```

!!! warning "Pre-1.0"
    Reads and writes are both available. **Writes are dry-run by default** —
    nothing changes without `--apply`. See [Writes](writes.md). While on `0.x`,
    minor versions may include breaking changes.

## Highlights

- **Mirrors the real API** — commands come from the SDK's vAPI metadata, covering
  vCenter and NSX from one generator.
- **Ergonomic** — tab-completion (enums, formats, profiles, filter choices, and
  opt-in [live resource ids](usage.md#live-resource-id-completion-opt-in)),
  per-field `--<field>` filter flags, and paging (`--all` / `--max-items` /
  `--limit`).
- **pyVmomi fallback** — read-only `perf`, `events`, `tasks`, and `inventory`
  commands for areas the REST/vAPI surface doesn't cover.
- **Safe by default** — writes are dry-run unless `--apply`; a dry-run never connects.
- **Agent-friendly** — JSON output, stable error envelope, documented exit codes,
  bundled agent Skill.

See the [Design](design.md) for how dynamic generation works, and
[Commands](commands.md) for the full surface.

## Install

```sh
uv tool install vcf-super-cli       # or: pip install vcf-super-cli
vsc --install-completion            # optional: offline shell completion
```

From source:

```sh
uv sync
uv run vsc --help
```
