"""Business-logic / orchestration layer.

Routers stay thin and delegate everything but request parsing + response
serialisation to these services. Cross-cutting concerns (DB session,
external clients) come in via constructor / function args -- never via
module-level singletons -- so unit tests can drop in fakes.
"""
from __future__ import annotations
