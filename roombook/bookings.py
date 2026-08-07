import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .auth import login_required
from .db import get_db

bp = Blueprint("bookings", __name__)

REPEAT_CHOICES = {
    "none": (0, "Does not repeat"),
    "weekly": (1, "Every week"),
    "fortnightly": (2, "Every 2 weeks"),
    "fourweekly": (4, "Every 4 weeks"),
}


def hm_to_minutes(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def minutes_to_hm(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def today_local():
    return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).date()


def boundaries():
    """All slot boundary times from DAY_START to DAY_END inclusive."""
    start = hm_to_minutes(current_app.config["DAY_START"])
    end = hm_to_minutes(current_app.config["DAY_END"])
    step = current_app.config["SLOT_MINUTES"]
    return [minutes_to_hm(m) for m in range(start, end + 1, step)]


def active_rooms(db):
    return db.execute(
        "SELECT * FROM rooms WHERE is_active = 1 ORDER BY sort_order, name"
    ).fetchall()


def find_conflict(db, room_id, day, start, end, exclude_id=None):
    """Return one existing booking overlapping [start, end) in this room on this day."""
    query = (
        "SELECT b.*, u.full_name FROM bookings b JOIN users u ON u.id = b.user_id "
        "WHERE b.room_id = ? AND b.date = ? AND b.start_time < ? AND b.end_time > ?"
    )
    args = [room_id, day, end, start]
    if exclude_id is not None:
        query += " AND b.id != ?"
        args.append(exclude_id)
    return db.execute(query + " LIMIT 1", args).fetchone()


def expand_dates(first, interval_weeks, until):
    days = []
    d = first
    while d <= until:
        days.append(d)
        d += timedelta(weeks=interval_weeks)
    return days


def pretty_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%a %d %b %Y")


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@bp.route("/day")
@bp.route("/day/<day>")
@login_required
def day(day=None):
    day = day or request.args.get("day")
    parsed = _parse_date(day) if day else today_local()
    if parsed is None:
        abort(404)
    day = parsed.isoformat()
    db = get_db()
    rooms = active_rooms(db)
    rows = db.execute(
        "SELECT b.*, u.full_name FROM bookings b JOIN users u ON u.id = b.user_id "
        "WHERE b.date = ? ORDER BY b.start_time",
        (day,),
    ).fetchall()

    win_start = hm_to_minutes(current_app.config["DAY_START"])
    win_end = hm_to_minutes(current_app.config["DAY_END"])
    span = win_end - win_start

    by_room = {}
    for row in rows:
        start = max(hm_to_minutes(row["start_time"]), win_start)
        end = min(hm_to_minutes(row["end_time"]), win_end)
        if end <= start:
            continue  # entirely outside the visible window
        by_room.setdefault(row["room_id"], []).append(
            {
                "row": row,
                "top": round((start - win_start) / span * 100, 3),
                "height": round((end - start) / span * 100, 3),
                "mine": row["user_id"] == g.user["id"],
            }
        )

    columns = [{"room": room, "blocks": by_room.get(room["id"], [])} for room in rooms]
    starts = boundaries()[:-1]
    return render_template(
        "day.html",
        day=day,
        day_label=parsed.strftime("%A %d %B %Y"),
        prev_day=(parsed - timedelta(days=1)).isoformat(),
        next_day=(parsed + timedelta(days=1)).isoformat(),
        today=today_local().isoformat(),
        columns=columns,
        starts=starts,
        n_slots=len(starts),
    )


def _validate_booking_form(db, form, allow_repeat=True, exclude_id=None):
    """Validate the booking form. Returns (data, errors)."""
    errors = []
    data = {
        "room_id": form.get("room_id", ""),
        "date": form.get("date", ""),
        "start": form.get("start", ""),
        "end": form.get("end", ""),
        "title": form.get("title", "").strip(),
        "notes": form.get("notes", "").strip(),
        "repeat": form.get("repeat", "none") if allow_repeat else "none",
        "until": form.get("until", ""),
        "skip_conflicts": form.get("skip_conflicts") == "1",
    }

    room = None
    if data["room_id"].isdigit():
        room = db.execute(
            "SELECT * FROM rooms WHERE id = ? AND is_active = 1", (data["room_id"],)
        ).fetchone()
    if room is None:
        errors.append("Choose a valid room.")

    first_day = _parse_date(data["date"])
    if first_day is None:
        errors.append("Choose a valid date.")
    elif first_day < today_local() and not g.user["is_admin"]:
        errors.append("You cannot book a date in the past.")

    valid_times = boundaries()
    if data["start"] not in valid_times[:-1] or data["end"] not in valid_times[1:]:
        errors.append("Choose valid start and end times.")
    elif data["start"] >= data["end"]:
        errors.append("End time must be after start time.")

    if not data["title"]:
        errors.append("Give the booking a short title (e.g. 'Diabetes clinic').")
    elif len(data["title"]) > 120:
        errors.append("Title must be 120 characters or fewer.")

    if data["repeat"] not in REPEAT_CHOICES:
        errors.append("Choose a valid repeat option.")
        data["repeat"] = "none"

    occurrences = []
    if not errors:
        interval = REPEAT_CHOICES[data["repeat"]][0]
        if interval == 0:
            occurrences = [first_day]
        else:
            until = _parse_date(data["until"])
            if until is None:
                errors.append("Choose an end date for the repeating booking.")
            elif until < first_day:
                errors.append("The repeat end date must be on or after the first booking date.")
            elif (until - first_day).days > 366:
                errors.append("Repeating bookings are limited to one year. Choose an earlier end date.")
            else:
                occurrences = expand_dates(first_day, interval, until)
                if len(occurrences) > current_app.config["MAX_OCCURRENCES"]:
                    errors.append(
                        f"That would create {len(occurrences)} bookings "
                        f"(maximum {current_app.config['MAX_OCCURRENCES']}). Choose an earlier end date."
                    )
                    occurrences = []

    data["room"] = room
    data["occurrences"] = occurrences
    return data, errors


@bp.route("/book", methods=("GET", "POST"))
@login_required
def book():
    db = get_db()
    rooms = active_rooms(db)
    valid_times = boundaries()

    if request.method == "POST":
        data, errors = _validate_booking_form(db, request.form)
        if not errors:
            conflicts = []
            clear_days = []
            for d in data["occurrences"]:
                clash = find_conflict(
                    db, data["room"]["id"], d.isoformat(), data["start"], data["end"]
                )
                if clash:
                    conflicts.append((d, clash))
                else:
                    clear_days.append(d)

            if conflicts and not data["skip_conflicts"]:
                for d, clash in conflicts[:5]:
                    errors.append(
                        f"{pretty_date(d.isoformat())}: clashes with "
                        f"{clash['start_time']}–{clash['end_time']} "
                        f"“{clash['title']}” ({clash['full_name']})."
                    )
                if len(conflicts) > 5:
                    errors.append(f"...and {len(conflicts) - 5} more clashes.")
                if len(data["occurrences"]) > 1:
                    errors.append(
                        "Tick “skip clashing dates” to book the free dates anyway."
                    )
            elif not clear_days:
                errors.append("Every requested date clashes with an existing booking.")
            else:
                series_id = str(uuid.uuid4()) if len(data["occurrences"]) > 1 else None
                for d in clear_days:
                    db.execute(
                        "INSERT INTO bookings (room_id, user_id, title, notes, date, start_time, end_time, series_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            data["room"]["id"],
                            g.user["id"],
                            data["title"],
                            data["notes"],
                            d.isoformat(),
                            data["start"],
                            data["end"],
                            series_id,
                        ),
                    )
                db.commit()
                message = f"Booked {data['room']['name']} × {len(clear_days)} "
                message += "date." if len(clear_days) == 1 else "dates."
                if conflicts:
                    skipped = ", ".join(pretty_date(d.isoformat()) for d, _ in conflicts)
                    message += f" Skipped clashing dates: {skipped}."
                flash(message, "success")
                return redirect(url_for("bookings.day", day=clear_days[0].isoformat()))
        return (
            render_template(
                "book_form.html",
                rooms=rooms,
                valid_times=valid_times,
                form=data,
                errors=errors,
                repeat_choices=REPEAT_CHOICES,
                min_date=today_local().isoformat(),
            ),
            400,
        )

    # GET: prefill from the grid link (room, date, start)
    start = request.args.get("start", "09:00")
    if start not in valid_times[:-1]:
        start = valid_times[0]
    default_end = minutes_to_hm(
        min(hm_to_minutes(start) + 60, hm_to_minutes(valid_times[-1]))
    )
    form = {
        "room_id": request.args.get("room_id", ""),
        "date": request.args.get("date", today_local().isoformat()),
        "start": start,
        "end": default_end,
        "title": "",
        "notes": "",
        "repeat": "none",
        "until": "",
        "skip_conflicts": False,
    }
    return render_template(
        "book_form.html",
        rooms=rooms,
        valid_times=valid_times,
        form=form,
        errors=[],
        repeat_choices=REPEAT_CHOICES,
        min_date=today_local().isoformat(),
    )


def _get_booking_or_404(booking_id):
    row = (
        get_db()
        .execute(
            "SELECT b.*, u.full_name, r.name AS room_name FROM bookings b "
            "JOIN users u ON u.id = b.user_id JOIN rooms r ON r.id = b.room_id "
            "WHERE b.id = ?",
            (booking_id,),
        )
        .fetchone()
    )
    if row is None:
        abort(404)
    return row


def _can_manage(booking):
    return g.user["is_admin"] or booking["user_id"] == g.user["id"]


@bp.route("/bookings/<int:booking_id>")
@login_required
def detail(booking_id):
    booking = _get_booking_or_404(booking_id)
    series_future = 0
    series_total = 0
    if booking["series_id"]:
        db = get_db()
        series_total = db.execute(
            "SELECT COUNT(*) FROM bookings WHERE series_id = ?", (booking["series_id"],)
        ).fetchone()[0]
        series_future = db.execute(
            "SELECT COUNT(*) FROM bookings WHERE series_id = ? AND date >= ?",
            (booking["series_id"], booking["date"]),
        ).fetchone()[0]
    return render_template(
        "booking_detail.html",
        booking=booking,
        can_manage=_can_manage(booking),
        series_total=series_total,
        series_future=series_future,
        pretty_date=pretty_date,
    )


@bp.post("/bookings/<int:booking_id>/cancel")
@login_required
def cancel(booking_id):
    booking = _get_booking_or_404(booking_id)
    if not _can_manage(booking):
        abort(403)
    db = get_db()
    db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    db.commit()
    flash(f"Cancelled {booking['room_name']} on {pretty_date(booking['date'])}.", "success")
    return redirect(url_for("bookings.day", day=booking["date"]))


@bp.post("/bookings/<int:booking_id>/cancel-future")
@login_required
def cancel_future(booking_id):
    booking = _get_booking_or_404(booking_id)
    if not _can_manage(booking) or not booking["series_id"]:
        abort(403)
    db = get_db()
    cur = db.execute(
        "DELETE FROM bookings WHERE series_id = ? AND date >= ?",
        (booking["series_id"], booking["date"]),
    )
    db.commit()
    flash(f"Cancelled {cur.rowcount} bookings from {pretty_date(booking['date'])} onwards.", "success")
    return redirect(url_for("bookings.day", day=booking["date"]))


@bp.post("/bookings/<int:booking_id>/cancel-series")
@login_required
def cancel_series(booking_id):
    booking = _get_booking_or_404(booking_id)
    if not _can_manage(booking) or not booking["series_id"]:
        abort(403)
    db = get_db()
    cur = db.execute(
        "DELETE FROM bookings WHERE series_id = ?", (booking["series_id"],)
    )
    db.commit()
    flash(f"Cancelled the whole series ({cur.rowcount} bookings).", "success")
    return redirect(url_for("bookings.day", day=booking["date"]))


@bp.route("/bookings/<int:booking_id>/edit", methods=("GET", "POST"))
@login_required
def edit(booking_id):
    booking = _get_booking_or_404(booking_id)
    if not _can_manage(booking):
        abort(403)
    db = get_db()
    rooms = active_rooms(db)
    valid_times = boundaries()

    if request.method == "POST":
        data, errors = _validate_booking_form(db, request.form, allow_repeat=False)
        if not errors:
            clash = find_conflict(
                db,
                data["room"]["id"],
                data["date"],
                data["start"],
                data["end"],
                exclude_id=booking_id,
            )
            if clash:
                errors.append(
                    f"Clashes with {clash['start_time']}–{clash['end_time']} "
                    f"“{clash['title']}” ({clash['full_name']})."
                )
            else:
                db.execute(
                    "UPDATE bookings SET room_id = ?, date = ?, start_time = ?, end_time = ?, "
                    "title = ?, notes = ? WHERE id = ?",
                    (
                        data["room"]["id"],
                        data["date"],
                        data["start"],
                        data["end"],
                        data["title"],
                        data["notes"],
                        booking_id,
                    ),
                )
                db.commit()
                flash("Booking updated.", "success")
                return redirect(url_for("bookings.detail", booking_id=booking_id))
        return (
            render_template(
                "edit_booking.html",
                booking=booking,
                rooms=rooms,
                valid_times=valid_times,
                form=data,
                errors=errors,
                min_date=today_local().isoformat(),
            ),
            400,
        )

    form = {
        "room_id": str(booking["room_id"]),
        "date": booking["date"],
        "start": booking["start_time"],
        "end": booking["end_time"],
        "title": booking["title"],
        "notes": booking["notes"],
    }
    return render_template(
        "edit_booking.html",
        booking=booking,
        rooms=rooms,
        valid_times=valid_times,
        form=form,
        errors=[],
        min_date=today_local().isoformat(),
    )


@bp.route("/my")
@login_required
def my_bookings():
    db = get_db()
    rows = db.execute(
        "SELECT b.*, r.name AS room_name FROM bookings b JOIN rooms r ON r.id = b.room_id "
        "WHERE b.user_id = ? AND b.date >= ? ORDER BY b.date, b.start_time",
        (g.user["id"], today_local().isoformat()),
    ).fetchall()
    return render_template("my.html", bookings=rows, pretty_date=pretty_date)
