import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import importlib

from app.core.deps import get_db
from app.db.base_class import Base
from app.main import app

importlib.import_module("app.models")  # registers all models on Base.metadata, without rebinding `app`


@pytest.fixture()
def db_session():
    """
    A fresh in-memory SQLite database per test, with foreign keys enforced
    (SQLite has them off by default) so cascade/restrict behavior is
    actually exercised the way it would be on Postgres.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, name: str, email: str, password: str = "SuperSecret123") -> dict:
    """Helper: registers a user, logs in, returns {"user": ..., "token": ..., "headers": ...}."""
    client.post("/auth/register", json={"name": name, "email": email, "password": password})
    resp = client.post("/auth/login", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    return {"user": me, "token": token, "headers": {"Authorization": f"Bearer {token}"}}


def unique_email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
