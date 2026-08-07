from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.security import generate_password_hash

from .auth import MIN_PASSWORD_LENGTH, admin_required
from .db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/rooms")
@admin_required
def rooms():
    all_rooms = get_db().execute(
        "SELECT * FROM rooms ORDER BY sort_order, name"
    ).fetchall()
    return render_template("admin/rooms.html", rooms=all_rooms)


@bp.post("/rooms/add")
@admin_required
def add_room():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Room name is required.", "error")
    else:
        db = get_db()
        exists = db.execute("SELECT 1 FROM rooms WHERE name = ?", (name,)).fetchone()
        if exists:
            flash("A room with that name already exists.", "error")
        else:
            max_sort = db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM rooms").fetchone()[0]
            db.execute(
                "INSERT INTO rooms (name, sort_order) VALUES (?, ?)", (name, max_sort + 1)
            )
            db.commit()
            flash(f"Added room '{name}'.", "success")
    return redirect(url_for("admin.rooms"))


@bp.post("/rooms/<int:room_id>")
@admin_required
def update_room(room_id):
    db = get_db()
    room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        flash("Room not found.", "error")
        return redirect(url_for("admin.rooms"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("Room name is required.", "error")
        return redirect(url_for("admin.rooms"))
    clash = db.execute(
        "SELECT 1 FROM rooms WHERE name = ? AND id != ?", (name, room_id)
    ).fetchone()
    if clash:
        flash("A room with that name already exists.", "error")
        return redirect(url_for("admin.rooms"))
    capacity = request.form.get("capacity", "").strip()
    sort_order = request.form.get("sort_order", "").strip()
    db.execute(
        "UPDATE rooms SET name = ?, description = ?, capacity = ?, sort_order = ?, is_active = ? "
        "WHERE id = ?",
        (
            name,
            request.form.get("description", "").strip(),
            int(capacity) if capacity.isdigit() else None,
            int(sort_order) if sort_order.lstrip("-").isdigit() else room["sort_order"],
            1 if request.form.get("is_active") == "1" else 0,
            room_id,
        ),
    )
    db.commit()
    flash(f"Updated room '{name}'.", "success")
    return redirect(url_for("admin.rooms"))


@bp.route("/users")
@admin_required
def users():
    all_users = get_db().execute(
        "SELECT * FROM users ORDER BY is_active DESC, username"
    ).fetchall()
    return render_template("admin/users.html", users=all_users)


@bp.post("/users/add")
@admin_required
def add_user():
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    if not username or not full_name:
        flash("Username and full name are required.", "error")
    elif len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
    else:
        db = get_db()
        exists = db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            flash("That username is already taken.", "error")
        else:
            db.execute(
                "INSERT INTO users (username, full_name, email, password_hash, is_admin) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    username,
                    full_name,
                    request.form.get("email", "").strip(),
                    generate_password_hash(password),
                    1 if request.form.get("is_admin") == "1" else 0,
                ),
            )
            db.commit()
            flash(f"Created user '{username}'.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/update")
@admin_required
def update_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    is_admin = 1 if request.form.get("is_admin") == "1" else 0
    is_active = 1 if request.form.get("is_active") == "1" else 0
    if user_id == g.user["id"] and (not is_admin or not is_active):
        flash("You cannot deactivate or remove admin from your own account.", "error")
        return redirect(url_for("admin.users"))
    full_name = request.form.get("full_name", "").strip() or user["full_name"]
    db.execute(
        "UPDATE users SET full_name = ?, email = ?, is_admin = ?, is_active = ? WHERE id = ?",
        (full_name, request.form.get("email", "").strip(), is_admin, is_active, user_id),
    )
    db.commit()
    flash(f"Updated user '{user['username']}'.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/password")
@admin_required
def reset_password(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    password = request.form.get("password", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
    else:
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        db.commit()
        flash(f"Password reset for '{user['username']}'.", "success")
    return redirect(url_for("admin.users"))
