"""Curated pyVmomi (SOAP) fallback commands for gaps the vAPI/REST surface lacks.

These are hand-written read-only commands mounted under ``vsc vsphere`` (perf,
events, tasks, inventory). They share the SmartConnect wrapper in
``vsc.connect.vmomi`` and emit through the same output contract as the generated
commands. No writes here — nothing needs ``--apply``.
"""
