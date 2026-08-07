CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    full_name TEXT NOT NULL,
    email TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    capacity INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,          -- YYYY-MM-DD
    start_time TEXT NOT NULL,    -- HH:MM, 24h
    end_time TEXT NOT NULL,      -- HH:MM, 24h, exclusive
    series_id TEXT,              -- shared UUID for recurring bookings, NULL for one-offs
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bookings_room_date ON bookings(room_id, date);
CREATE INDEX IF NOT EXISTS idx_bookings_series ON bookings(series_id);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
