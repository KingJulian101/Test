import os

from flask import Flask, redirect, url_for


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get(
            "DATABASE", os.path.join(app.instance_path, "roombook.sqlite")
        ),
        SITE_NAME=os.environ.get("SITE_NAME", "Room Booking"),
        TIMEZONE=os.environ.get("TIMEZONE", "Europe/London"),
        DAY_START=os.environ.get("DAY_START", "07:00"),
        DAY_END=os.environ.get("DAY_END", "20:00"),
        SLOT_MINUTES=int(os.environ.get("SLOT_MINUTES", "15")),
        MAX_OCCURRENCES=int(os.environ.get("MAX_OCCURRENCES", "53")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import admin, auth, bookings, db

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(bookings.bp)
    app.register_blueprint(admin.bp)

    @app.route("/")
    def index():
        return redirect(url_for("bookings.day"))

    return app
