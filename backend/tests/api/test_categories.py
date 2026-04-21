"""Tests for ``GET /categories``."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Category


def test_categories_empty_tree(client: TestClient) -> None:
    response = client.get("/categories")
    assert response.status_code == 200
    assert response.json() == {"roots": []}


def test_categories_tree_shape(client: TestClient, api_db_session: Session) -> None:
    root = Category(name="반려동물용품")
    api_db_session.add(root)
    api_db_session.flush()

    child_a = Category(name="사료", parent_id=root.id)
    child_b = Category(name="간식", parent_id=root.id, is_certification_required=True)
    api_db_session.add_all([child_a, child_b])
    api_db_session.commit()

    response = client.get("/categories")
    assert response.status_code == 200
    body = response.json()
    assert len(body["roots"]) == 1
    root_node = body["roots"][0]
    assert root_node["name"] == "반려동물용품"
    child_names = sorted(child["name"] for child in root_node["children"])
    assert child_names == ["간식", "사료"]
    # Certification flag preserved
    cert_map = {
        child["name"]: child["is_certification_required"]
        for child in root_node["children"]
    }
    assert cert_map == {"사료": False, "간식": True}
