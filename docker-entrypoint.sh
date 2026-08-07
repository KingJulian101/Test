#!/bin/sh
set -e

if [ ! -f "$DATABASE" ]; then
    echo "No database found at $DATABASE - initialising..."
    flask --app roombook init-db
    if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
        flask --app roombook create-admin "$ADMIN_USERNAME" "$ADMIN_PASSWORD" \
            --full-name "${ADMIN_FULL_NAME:-Administrator}"
    else
        echo "WARNING: ADMIN_USERNAME/ADMIN_PASSWORD not set - no admin user created."
        echo "Run: docker compose exec app flask --app roombook create-admin <user> <password>"
    fi
fi

# Single worker + threads so the in-process login throttle sees all requests
# and SQLite writes stay serialised.
exec gunicorn --workers 1 --threads 8 --bind 0.0.0.0:8000 "roombook:create_app()"
