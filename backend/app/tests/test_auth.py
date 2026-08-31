from app.tests.conftest import unique_email


def test_register_login_me_flow(client):
    email = unique_email("anwita")
    r = client.post("/auth/register", json={"name": "Anwita", "email": email, "password": "SuperSecret123"})
    assert r.status_code == 201
    assert r.json()["email"] == email
    assert "password" not in r.json()
    assert "password_hash" not in r.json()

    r = client.post("/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_duplicate_registration_returns_409(client):
    email = unique_email("dupe")
    client.post("/auth/register", json={"name": "A", "email": email, "password": "SuperSecret123"})
    r = client.post("/auth/register", json={"name": "A", "email": email, "password": "SuperSecret123"})
    assert r.status_code == 409


def test_login_wrong_password_returns_401(client):
    email = unique_email("wrongpw")
    client.post("/auth/register", json={"name": "A", "email": email, "password": "SuperSecret123"})
    r = client.post("/auth/login", json={"email": email, "password": "WrongPassword"})
    assert r.status_code == 401


def test_me_without_token_returns_401(client):
    r = client.get("/auth/me")
    assert r.status_code in (401, 403)  # HTTPBearer returns 403 if header missing entirely, 401 if invalid


def test_me_with_garbage_token_returns_401(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
