"""NOVA governed agent runtime (see docs/ADR/0001-agent-runtime-split.md).

Phase 1 foundation. This package is deliberately NOT wired into the Brain,
the service container, or the Initiative Engine yet. Importing it must have no
side effects. It never imports the legacy intent-router package, and NOVA boots
identically whether or not this package is present.
"""
