"""
Test fixtures for Sistema Drop unit tests.

Strategy:
- Set dummy env vars BEFORE any app import (Oracle engine is lazy — won't connect)
- MockDB mimics AsyncSyncSession interface without hitting Oracle
- get_db dependency is overridden in each test module
- APScheduler is patched to prevent background jobs from running during tests
"""
import os

# Must be set before any app import to satisfy Pydantic Settings validation
os.environ.setdefault("ORACLE_USER", "test_user")
os.environ.setdefault("ORACLE_PASSWORD", "test_password")
os.environ.setdefault("ORACLE_DSN", "test_dsn")
os.environ.setdefault("JWT_SECRET", "test_secret_key_for_unit_tests_only_32chars")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class MockResult:
    """Mimics SQLAlchemy CursorResult returned by db.execute()."""

    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class MockDB:
    """
    Mock implementation of AsyncSyncSession for unit tests.

    Usage in tests:
        mock_db.set_result(None)              # next execute returns None
        mock_db.set_result(some_user_object)  # next execute returns a User
    """

    def __init__(self):
        self._next_result = MockResult()
        self.committed = False
        self.rolled_back = False
        self.added = []
        self.deleted = []

    def set_result(self, value, rows=None):
        """Configure what the next db.execute() call will return."""
        self._next_result = MockResult(value=value, rows=rows or [])

    async def execute(self, *args, **kwargs):
        result = self._next_result
        self._next_result = MockResult()  # reset after use
        return result

    async def scalar(self, *args, **kwargs):
        return self._next_result.scalar_one_or_none()

    async def flush(self, *args, **kwargs):
        pass

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        pass

    async def refresh(self, instance, *args, **kwargs):
        pass

    def add(self, instance):
        self.added.append(instance)

    def delete(self, instance):
        self.deleted.append(instance)

    def reset(self):
        self.committed = False
        self.rolled_back = False
        self.added.clear()
        self.deleted.clear()
        self._next_result = MockResult()


@pytest.fixture
def mock_db():
    db = MockDB()
    yield db
    db.reset()


@pytest.fixture(scope="session")
def app():
    """FastAPI app instance with scheduler patched out."""
    with (
        patch("tasks.scheduler.start_scheduler"),
        patch("tasks.scheduler.stop_scheduler"),
    ):
        from main import app as fastapi_app
        yield fastapi_app


@pytest.fixture
def client(app, mock_db):
    """TestClient with get_db overridden to use MockDB."""
    from database import get_db

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
