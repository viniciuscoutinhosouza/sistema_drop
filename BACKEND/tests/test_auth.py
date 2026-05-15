"""
Auth endpoint unit tests — DB mocked, no Oracle connection required.
"""
from unittest.mock import MagicMock

import pytest


def _make_user(user_id=1, email="test@example.com", role="ac", is_active=True):
    """Build a mock User object."""
    from services.auth_service import hash_password
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.role = role
    user.is_active = is_active
    user.full_name = "Test User"
    user.password_hash = hash_password("senha123")
    user.dark_mode = False
    user.go_id = None
    user.warehouse_id = None
    return user


@pytest.mark.unit
def test_login_wrong_password(client, mock_db):
    """Login with correct email but wrong password returns 401."""
    mock_db.set_result(_make_user())

    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "senha_errada",
    })
    assert response.status_code == 401
    assert "incorretos" in response.json()["detail"]


@pytest.mark.unit
def test_login_user_not_found(client, mock_db):
    """Login with unknown email returns 401."""
    mock_db.set_result(None)  # no user in DB

    response = client.post("/api/v1/auth/login", json={
        "email": "naoexiste@example.com",
        "password": "qualquersenha",
    })
    assert response.status_code == 401


@pytest.mark.unit
def test_login_inactive_user(client, mock_db):
    """Login with inactive user returns 403."""
    mock_db.set_result(_make_user(is_active=False))

    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "senha123",
    })
    assert response.status_code == 403
    assert "desativada" in response.json()["detail"]


@pytest.mark.unit
def test_protected_endpoint_without_token(client):
    """Accessing a protected endpoint without a token returns 401."""
    response = client.get("/api/v1/users")
    assert response.status_code == 401


@pytest.mark.unit
def test_protected_endpoint_with_invalid_token(client):
    """Accessing a protected endpoint with a fake token returns 401."""
    response = client.get("/api/v1/users", headers={"Authorization": "Bearer fake_token_xyz"})
    assert response.status_code == 401


@pytest.mark.unit
def test_login_success(client, mock_db):
    """Successful login returns access and refresh tokens."""
    user = _make_user()
    mock_db.set_result(user)

    response = client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "senha123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["email"] == "test@example.com"
    assert data["role"] == "ac"
