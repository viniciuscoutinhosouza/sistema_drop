"""
Health and root endpoint tests — no auth, no DB required.
"""
import pytest


@pytest.mark.unit
def test_root_returns_ok(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "MIG ECOMMERCE" in data["system"]


@pytest.mark.unit
def test_docs_available(client):
    response = client.get("/docs")
    assert response.status_code == 200


@pytest.mark.unit
def test_openapi_schema_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "MIG ECOMMERCE API"
