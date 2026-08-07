from conftest import login


def test_login_required_redirects(client):
    response = client.get("/day")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_logout(client):
    response = login(client, "alice")
    assert response.status_code == 302
    response = client.get("/day")
    assert response.status_code == 200
    assert b"Alice Smith" in response.data

    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/day").status_code == 302


def test_bad_password_rejected(client):
    response = login(client, "alice", "wrong-password")
    assert b"Incorrect username or password" in response.data


def test_admin_pages_forbidden_for_normal_users(client):
    login(client, "alice")
    assert client.get("/admin/rooms").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_admin_pages_allowed_for_admin(client):
    login(client, "admin")
    assert client.get("/admin/rooms").status_code == 200
    assert client.get("/admin/users").status_code == 200
