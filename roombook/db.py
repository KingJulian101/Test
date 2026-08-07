import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


DEFAULT_ROOMS = [f"Room {i}" for i in range(1, 11)]


def init_db():
    db = get_db()
    db.executescript((Path(__file__).parent / "schema.sql").read_text())
    if db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        for i, name in enumerate(DEFAULT_ROOMS):
            db.execute("INSERT INTO rooms (name, sort_order) VALUES (?, ?)", (name, i))
    db.commit()


@click.command("init-db")
def init_db_command():
    """Create tables (safe to re-run) and seed 10 default rooms if none exist."""
    init_db()
    click.echo("Database initialised.")


@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@click.option("--full-name", default="Administrator")
def create_admin_command(username, password, full_name):
    """Create an admin user, or reset the password of an existing user and make them admin."""
    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    pw_hash = generate_password_hash(password)
    if existing:
        db.execute(
            "UPDATE users SET password_hash = ?, is_admin = 1, is_active = 1 WHERE id = ?",
            (pw_hash, existing["id"]),
        )
        click.echo(f"Updated existing user '{username}' (password reset, admin enabled).")
    else:
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, is_admin) VALUES (?, ?, ?, 1)",
            (username, full_name, pw_hash),
        )
        click.echo(f"Created admin user '{username}'.")
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
