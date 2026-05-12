"""Temporal activities — side-effectful steps called by workflows.

Each activity class holds a Container reference and resolves fresh
UoW + repos per invocation. Inputs/outputs are plain dataclasses
with JSON-serializable fields (str UUIDs, not UUID objects).
"""
