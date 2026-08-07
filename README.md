# RoomBook

A small, self-hosted room booking system for a GP practice (or any small
organisation) — a lightweight, self-hosted take on Skedda.

- **Skedda-style day grid** — all rooms side by side, click an empty slot to book it.
- **One-off and recurring bookings** — weekly, fortnightly or every 4 weeks, up to a year ahead, with clash detection (optionally skip clashing dates).
- **Self-serve** — staff log in, book, edit and cancel their own bookings; admins can manage anyone's.
- **Cancel one occurrence, this-and-future, or a whole series.**
- **Admin screens** — manage rooms (add/rename/deactivate, capacity, ordering) and users (add, reset password, deactivate, promote to admin).
- **Boring on purpose** — Python/Flask + a single SQLite file. No JavaScript frameworks, no external services, trivial to back up.

## Quick start (Docker, recommended)

```bash
cp .env.example .env
nano .env                  # set DOMAIN, SECRET_KEY, admin credentials
docker compose up -d --build
```

That starts the app plus a [Caddy](https://caddyserver.com/) reverse proxy which
automatically obtains and renews a Let's Encrypt certificate for `DOMAIN`.
On first start the database is created with 10 rooms (`Room 1`–`Room 10`) and
your admin account. Log in, rename the rooms under **Rooms**, and add your
staff under **Users**.

See **[docs/DEPLOY.md](docs/DEPLOY.md)** for the full guide: Proxmox setup,
DNS/IPv6, Cloudflare Tunnel (no open ports needed), backups and updates.

## Quick start (local development)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
flask --app roombook init-db
flask --app roombook create-admin admin changeme123 --full-name "Your Name"
flask --app roombook run --debug
```

Then open http://127.0.0.1:5000 and log in.

Run the tests with:

```bash
pytest
```

## Configuration

All optional, via environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | *(dev value)* | Session signing key — **must** be set in production |
| `SITE_NAME` | `Room Booking` | Name shown in the header |
| `DAY_START` / `DAY_END` | `07:00` / `20:00` | Bookable hours shown on the grid |
| `SLOT_MINUTES` | `15` | Slot granularity |
| `TIMEZONE` | `Europe/London` | Used to decide what "today" is |
| `DATABASE` | `instance/roombook.sqlite` | SQLite file path (`/data/roombook.sqlite` in Docker) |

## Notes for NHS / practice use

Bookings hold only room, time, a short title and the booker's name — keep
patient-identifiable data out of titles and notes as a matter of policy.
Still worth a quick word with your IG lead before going live, and see the
security notes in [docs/DEPLOY.md](docs/DEPLOY.md).
