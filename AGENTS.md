# AGENTS.md

Guidance for AI agents and contributors working in this repo.

## What this is

`vcf-super-cli` (`vsc`) — a CLI for VMware Cloud Foundation 9. The command tree is
**generated** by introspecting the `vcf-sdk` vAPI bindings (`vsc.gen`), not hand
written. Two product groups: `vsc vsphere …` (vCenter) and `vsc nsx …` (NSX Policy).

## Project conventions

- Python ≥3.12. Managed with **uv**. Build backend: hatchling.
- Lint/format: **ruff** (`uv run ruff check .`, `uv run ruff format .`).
- Types: **mypy --strict** (`uv run mypy vsc`).
- Tests: **pytest** (`uv run pytest`). Live-server tests live in `tests/e2e/`
  and are ignored by default.
- Output is JSON by default; errors use a stable envelope; exit codes are a frozen
  `IntEnum` in `vsc/output/exit_codes.py` — extend, never renumber.
- v0.1 is **read-only**. Writes (v0.2) must be dry-run by default, gated on `--apply`.

## Workflow

Work is **issue-driven**. One issue → one branch → PR → review → fix → merge.
Do not push directly to `main`. See open issues for the roadmap.

## Where things go

| Concern | Location |
|---------|----------|
| Entry point / Typer app | `vsc/cli/` |
| SDK introspection + command generation | `vsc/gen/` |
| Connections / auth | `vsc/connect/` |
| Profiles / config | `vsc/config/` |
| Output, errors, exit codes | `vsc/output/` |
| Bundled agent Skill | `skills/vcf-super-cli/` |
| Design spec | `docs/superpowers/specs/` |
