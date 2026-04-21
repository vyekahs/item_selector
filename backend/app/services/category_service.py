"""Category tree assembly for ``GET /categories``."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category
from app.schemas.responses.category import CategoryNode, CategoryResponse


def get_category_tree(session: Session) -> CategoryResponse:
    """Return the full category hierarchy as nested ``CategoryNode``s.

    The schema is small (~tens of rows in production) so we just load
    everything in one query and assemble in Python.
    """
    rows = session.execute(select(Category).order_by(Category.id)).scalars().all()
    nodes: dict[int, CategoryNode] = {
        c.id: CategoryNode(
            id=c.id,
            name=c.name,
            parent_id=c.parent_id,
            is_certification_required=bool(c.is_certification_required),
            children=[],
        )
        for c in rows
    }
    roots: list[CategoryNode] = []
    for category in rows:
        node = nodes[category.id]
        if category.parent_id and category.parent_id in nodes:
            nodes[category.parent_id].children.append(node)
        else:
            roots.append(node)
    return CategoryResponse(roots=roots)
