#!/bin/bash
set -e

PG_CONF="/etc/postgresql/14/main/postgresql.conf"
PG_HBA="/etc/postgresql/14/main/pg_hba.conf"

# 1. Listen on every address (already added earlier)
sed -ri "s/^#?listen_addresses\s*=.*/listen_addresses = '*'/" "$PG_CONF"

# 2. Allow password auth from everywhere (or change 0.0.0.0/0 to your subnet)
grep -q '^host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+0\.0\.0\.0/0' "$PG_HBA" \
  || echo "host all all 0.0.0.0/0 md5" >> "$PG_HBA"          #  ← NEW
grep -q '^host[[:space:]]\+all[[:space:]]\+all[[:space:]]\+::/0' "$PG_HBA" \
  || echo "host all all ::/0 md5"       >> "$PG_HBA"          #  ← NEW (IPv6)

# Start PostgreSQL
service postgresql start

# Wait for PostgreSQL to be ready
sleep 5

# Configure PostgreSQL - only create if they don't exist
if ! su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$POSTGRES_USER'\"" | grep -q 1; then
    echo "Creating user $POSTGRES_USER..."
    su postgres -c "psql --command \"CREATE USER $POSTGRES_USER WITH SUPERUSER PASSWORD '$POSTGRES_PASSWORD';\""
else
    echo "User $POSTGRES_USER already exists"
fi

if ! su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB'\"" | grep -q 1; then
    echo "Creating database $POSTGRES_DB..."
    su postgres -c "createdb -O $POSTGRES_USER $POSTGRES_DB"
else
    echo "Database $POSTGRES_DB already exists"
fi

# Keep the container running
exec "$@"