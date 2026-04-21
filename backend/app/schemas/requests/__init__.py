"""Request body / query schemas."""
from __future__ import annotations

from .feedback import FeedbackCreateRequest
from .product import ProductCreateRequest

__all__ = [
    "FeedbackCreateRequest",
    "ProductCreateRequest",
]
