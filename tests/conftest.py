import pytest
from werkzeug.security import generate_password_hash

from roombook import create_app
from roombook.db import get_db, init_db


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )
    with app.app_context():
        init_db()
        db = get_db()
        pw = generate_password_hash("password123")
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            ("admin", "Admin User", pw, 1),
        )
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            ("alice", "Alice Smith", pw, 0),
        )
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            ("bob", "Bob Jones", pw, 0),
        )
        db.commit()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password="password123"):
    return client.post(
        "/login", data={"username": username, "password": password}
    )
