def test_register_and_login(client):
    resp = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "supersecret1", "display_name": "A", "role": "parent"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "parent"

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "supersecret1"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password_rejected(client):
    client.post(
        "/auth/register",
        json={"email": "b@example.com", "password": "supersecret1", "display_name": "B", "role": "parent"},
    )
    resp = client.post("/auth/login", json={"email": "b@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_duplicate_registration_rejected(client):
    payload = {"email": "c@example.com", "password": "supersecret1", "display_name": "C", "role": "parent"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_protected_endpoint_requires_token(client):
    resp = client.post("/families", json={"name": "No Auth Family"})
    assert resp.status_code == 401
