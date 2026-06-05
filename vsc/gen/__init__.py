"""Command-tree generation from the vcf-sdk vAPI bindings.

The generator introspects installed ``VapiInterface`` service classes (vCenter and
NSX Policy), reads their embedded REST + type metadata, and assembles a Typer
command tree. It runs fully offline — no server or credentials are needed to build
``--help``.
"""
