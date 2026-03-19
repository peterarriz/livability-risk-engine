#!/usr/bin/env bash
# scripts/apply_schema.sh
# task: data-017
# lane: data
#
# Apply db/schema.sql to the live Railway (or any Postgres+PostGIS) database.
#
# Usage:
#   DATABASE_URL="postgres://..." ./scripts/apply_schema.sh
#
# Or with individual env vars:
#   POSTGRES_HOST=... POSTGRES_DB=... POSTGRES_USER=... POSTGRES_PASSWORD=... \
#     ./scripts/apply_schema.sh
#
# Prerequisites:
#   psql must be installed (apt install postgresql-client or brew install libpq)

set -euo pipefail

SCHEMA_FILE="$(dirname "$0")/../db/schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "ERROR: schema file not found at $SCHEMA_FILE" >&2
  exit 1
fi

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Applying schema using DATABASE_URL..."
  psql "$DATABASE_URL" -f "$SCHEMA_FILE"
else
  : "${POSTGRES_HOST:=localhost}"
  : "${POSTGRES_PORT:=5432}"
  : "${POSTGRES_DB:=livability}"
  : "${POSTGRES_USER:=postgres}"

  echo "Applying schema to ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}..."
  PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -f "$SCHEMA_FILE"
fi

echo "Schema applied successfully."
