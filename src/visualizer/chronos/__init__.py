"""Chronos -- a plotline & timeline API for fiction writers.

See ``docs/chronos/design.md`` for the design. The package is layered so the
interesting logic is pure and unit-testable:

- pure logic (no I/O): ``timeline``, ``conflicts``, ``ordering``, ``calendar``,
  ``book_rules``, ``validation``, ``models``.
- seams (injected I/O): ``store.StoryStore``, ``entity_gate.EntityGate``.
- orchestration: ``services`` (application services), ``presenters`` (response
  shaping), ``app`` (Flask factory).
"""
