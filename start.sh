#!/usr/bin/env bash
# start.sh — backend startup script for Railway.
# Must run from repo root so Python resolves the `backend` package correctly.
set -e
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
