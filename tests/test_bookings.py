from datetime import date, timedelta

from conftest import login

from roombook.db import get_db

NEXT_MONDAY = date.today() + timedelta(days=(7 - date.today().weekday()) or 7)


def book(client, **overrides):
    data = {
        "room_id": "1",
        "date": NEXT_MONDAY.isoformat(),
        "start": "09:00",
        "end": "10:00",
        "title": "Test clinic",
        "notes": "",
        "repeat": "none",
        "until": "",
    }
    data.update(overrides)
    return client.post("/book", data=data)


def count_bookings(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM bookings").fetchone()[0]


def test_create_one_off_booking(app, client):
    login(client, "alice")
    response = book(client)
    assert response.status_code == 302
    assert count_bookings(app) == 1


def test_conflicting_booking_rejected(app, client):
    login(client, "alice")
    book(client)
    response = book(client, start="09:30", end="10:30", title="Overlap")
    assert response.status_code == 400
    assert b"clashes with" in response.data
    assert count_bookings(app) == 1


def test_adjacent_bookings_allowed(app, client):
    login(client, "alice")
    book(client)
    response = book(client, start="10:00", end="11:00", title="Back to back")
    assert response.status_code == 302
    assert count_bookings(app) == 2


def test_same_time_different_room_allowed(app, client):
    login(client, "alice")
    book(client)
    response = book(client, room_id="2")
    assert response.status_code == 302
    assert count_bookings(app) == 2


def test_end_before_start_rejected(app, client):
    login(client, "alice")
    response = book(client, start="10:00", end="09:00")
    assert response.status_code == 400
    assert count_bookings(app) == 0


def test_past_date_rejected_for_normal_user(app, client):
    login(client, "alice")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = book(client, date=yesterday)
    assert response.status_code == 400
    assert count_bookings(app) == 0


def test_weekly_recurrence_creates_series(app, client):
    login(client, "alice")
    until = (NEXT_MONDAY + timedelta(weeks=3)).isoformat()
    response = book(client, repeat="weekly", until=until)
    assert response.status_code == 302
    assert count_bookings(app) == 4
    with app.app_context():
        series_ids = get_db().execute(
            "SELECT DISTINCT series_id FROM bookings"
        ).fetchall()
    assert len(series_ids) == 1
    assert series_ids[0][0] is not None


def test_recurrence_conflict_blocks_without_skip(app, client):
    login(client, "alice")
    clash_day = NEXT_MONDAY + timedelta(weeks=1)
    book(client, date=clash_day.isoformat(), title="Existing")
    until = (NEXT_MONDAY + timedelta(weeks=2)).isoformat()
    response = book(client, repeat="weekly", until=until, title="Series")
    assert response.status_code == 400
    assert count_bookings(app) == 1


def test_recurrence_skip_conflicts_books_free_dates(app, client):
    login(client, "alice")
    clash_day = NEXT_MONDAY + timedelta(weeks=1)
    book(client, date=clash_day.isoformat(), title="Existing")
    until = (NEXT_MONDAY + timedelta(weeks=2)).isoformat()
    response = book(
        client, repeat="weekly", until=until, title="Series", skip_conflicts="1"
    )
    assert response.status_code == 302
    # 1 existing + 2 of the 3 series dates (the clashing one skipped)
    assert count_bookings(app) == 3


def test_owner_can_cancel(app, client):
    login(client, "alice")
    book(client)
    response = client.post("/bookings/1/cancel")
    assert response.status_code == 302
    assert count_bookings(app) == 0


def test_non_owner_cannot_cancel(app, client):
    login(client, "alice")
    book(client)
    client.post("/logout")
    login(client, "bob")
    response = client.post("/bookings/1/cancel")
    assert response.status_code == 403
    assert count_bookings(app) == 1


def test_admin_can_cancel_any_booking(app, client):
    login(client, "alice")
    book(client)
    client.post("/logout")
    login(client, "admin")
    response = client.post("/bookings/1/cancel")
    assert response.status_code == 302
    assert count_bookings(app) == 0


def test_cancel_future_keeps_earlier_occurrences(app, client):
    login(client, "alice")
    until = (NEXT_MONDAY + timedelta(weeks=3)).isoformat()
    book(client, repeat="weekly", until=until)
    assert count_bookings(app) == 4
    with app.app_context():
        third = get_db().execute(
            "SELECT id FROM bookings ORDER BY date LIMIT 1 OFFSET 2"
        ).fetchone()
    response = client.post(f"/bookings/{third['id']}/cancel-future")
    assert response.status_code == 302
    assert count_bookings(app) == 2


def test_cancel_series_removes_all(app, client):
    login(client, "alice")
    until = (NEXT_MONDAY + timedelta(weeks=3)).isoformat()
    book(client, repeat="weekly", until=until)
    response = client.post("/bookings/1/cancel-series")
    assert response.status_code == 302
    assert count_bookings(app) == 0


def test_edit_rejects_clash(app, client):
    login(client, "alice")
    book(client)
    book(client, start="11:00", end="12:00", title="Second")
    response = client.post(
        "/bookings/2/edit",
        data={
            "room_id": "1",
            "date": NEXT_MONDAY.isoformat(),
            "start": "09:30",
            "end": "10:30",
            "title": "Second",
            "notes": "",
        },
    )
    assert response.status_code == 400
    assert b"Clashes with" in response.data


def test_edit_moves_booking(app, client):
    login(client, "alice")
    book(client)
    response = client.post(
        "/bookings/1/edit",
        data={
            "room_id": "2",
            "date": NEXT_MONDAY.isoformat(),
            "start": "14:00",
            "end": "15:00",
            "title": "Moved",
            "notes": "",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        row = get_db().execute("SELECT * FROM bookings WHERE id = 1").fetchone()
    assert row["room_id"] == 2
    assert row["start_time"] == "14:00"
    assert row["title"] == "Moved"
