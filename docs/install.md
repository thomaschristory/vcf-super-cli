# Install

`vsc` targets Python ≥ 3.12.

## From PyPI (once published)

```sh
uv tool install vcf-super-cli
# or
pipx install vcf-super-cli
```

Both console scripts are installed: `vcf-super-cli` and the short alias `vsc`.

## From source

```sh
git clone https://github.com/thomaschristory/vcf-super-cli
cd vcf-super-cli
uv sync
uv run vsc --help
```

## Shell completion

```sh
vsc --install-completion     # auto-detects your shell
vsc --show-completion        # print the script instead of installing
```

## First run

The command tree is generated from the installed `vcf-sdk` and works offline, so
`vsc --help` and every `--help` page render without a server or credentials:

```sh
vsc --help
vsc vsphere --help
vsc vsphere vm list --help
```

To actually talk to a vCenter/NSX, configure a [profile](profiles.md).
