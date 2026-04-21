"""Pydantic request/response schemas for the public HTTP API.

DTOs in :mod:`app.contracts.dto` (owned by Data Collection Agent) describe
the *upstream* data shape. The schemas here describe the *frontend-facing*
shape -- they may add/remove fields, rename, denormalise, etc. so the
front-end never has to care about source-API quirks.
"""
from __future__ import annotations
