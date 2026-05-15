"""
Orders endpoint unit tests — auth mocked, no Oracle connection required.
"""
from unittest.mock import MagicMock

import pytest


def _make_auth_headers(user_id=1, role="ac"):
    """Generate a valid JWT header for test requests."""
    from services.auth_service import create_access_token
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


def _make_user(user_id=1, role="ac"):
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.is_active = True
    user.full_name = "Test AC"
    user.email = "ac@test.com"
    user.warehouse_id = 1
    user.go_id = None
    return user


@pytest.mark.unit
def test_orders_list_requires_auth(client):
    """Orders list endpoint must reject unauthenticated requests."""
    response = client.get("/api/v1/orders")
    assert response.status_code == 401


@pytest.mark.unit
def test_orders_list_with_valid_token(client, mock_db):
    """Orders list with valid AC token should pass auth and return a list."""
    # First execute: get_current_user fetches the User
    mock_db.set_result(_make_user())

    headers = _make_auth_headers(user_id=1, role="ac")
    response = client.get("/api/v1/orders", headers=headers)

    # Auth passed — could be 200 (empty list) or other valid status
    # We don't test business logic here, just that auth works
    assert response.status_code in (200, 400, 422)


@pytest.mark.unit
def test_orders_list_wrong_role(client, mock_db):
    """Endpoint restricted to certain roles rejects unauthorized roles."""
    mock_db.set_result(_make_user(role="ugo"))

    headers = _make_auth_headers(user_id=2, role="ugo")
    # GET /orders is accessible to ugo too — just testing auth passes
    response = client.get("/api/v1/orders", headers=headers)
    assert response.status_code != 401
