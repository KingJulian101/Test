import functools
import secrets
import threading
import time

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LENGTH = 8
LOCKOUT_TRIES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60

# Best-effort in-process login throttle; run gunicorn with a single worker
# (threads for concurrency) so all requests share it.
_failed_logins = {}
_failed_lock = threading.Lock()


def _locked_out(key):
    now = time.time()
    with _failed_lock:
        recent = [t for t in _failed_logins.get(key, []) if now - t < LOCKOUT_WINDOW_SECONDS]
        _failed_logins[key] = recent
        return len(recent) >= LOCKOUT_TRIES


def _record_failure(key):
    with _failed_lock:
        _failed_logins.setdefault(key, []).append(time.time())


def _clear_failures(key):
    with _failed_lock:
        _failed_logins.pop(key, None)


@bp.app_template_global("csrf_token")
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


@bp.before_app_request
def check_csrf():
    if request.method == "POST" and not current_app.config.get("TESTING"):
        token = session.get("_csrf")
        if not token or request.form.get("_csrf") != token:
            abort(400, description="Invalid or missing CSRF token. Reload the page and try again.")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = (
            get_db()
            .execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
            .fetchone()
        )


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        if not g.user["is_admin"]:
            abort(403)
        return view(**kwargs)

    return wrapped


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("bookings.day"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = username.lower()
        if _locked_out(key):
            flash("Too many failed attempts. Try again in 15 minutes.", "error")
            return render_template("login.html")
        user = (
            get_db()
            .execute("SELECT * FROM users WHERE username = ?", (username,))
            .fetchone()
        )
        if (
            user is None
            or not user["is_active"]
            or not check_password_hash(user["password_hash"], password)
        ):
            _record_failure(key)
            flash("Incorrect username or password.", "error")
            return render_template("login.html")
        _clear_failures(key)
        session.clear()
        session["user_id"] = user["id"]
        target = request.args.get("next", "")
        if not target.startswith("/") or target.startswith("//"):
            target = url_for("bookings.day")
        return redirect(target)
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=("GET", "POST"))
@login_required
def account():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(g.user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < MIN_PASSWORD_LENGTH:
            flash(f"New password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), g.user["id"]),
            )
            db.commit()
            flash("Password updated.", "success")
            return redirect(url_for("auth.account"))
    return render_template("account.html")
