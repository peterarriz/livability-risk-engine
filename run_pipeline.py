"""
run_pipeline.py
task: data-017
lane: data

Full end-to-end ingest pipeline orchestrator for the Chicago MVP.

Runs all ingest steps in order:
  1. Fetch building permits from Chicago Socrata API       → data/raw/building_permits.json
  2. Fetch street closures from Chicago Socrata API        → data/raw/street_closures.json
  3. Fetch IDOT road construction from ArcGIS REST API     → data/raw/idot_road_projects.json
  4. Fetch IL city permits (Cook County + IL cities)       → data/raw/il_city_permits_*.json
  5. Fill missing lat/lon via geocoding                    → updates staging files in place
  6. Load normalized records into the DB                   → upserts into `projects` table

Usage:
  # Full pipeline (requires DATABASE_URL or POSTGRES_* env vars)
  python run_pipeline.py

  # Skip geocoding fill (faster; use only if staging files already have coords)
  python run_pipeline.py --skip-geocode

  # Dry-run: fetch data but do not write to DB
  python run_pipeline.py --dry-run

  # Prune completed records older than 90 days after loading
  python run_pipeline.py --prune-days 90

Environment variables:
  DATABASE_URL             — Full Postgres connection string (Railway/Heroku standard)
                             If set, takes precedence over POSTGRES_* vars.
  POSTGRES_HOST            — (default: localhost)
  POSTGRES_PORT            — (default: 5432)
  POSTGRES_DB              — (default: livability)
  POSTGRES_USER            — (default: postgres)
  POSTGRES_PASSWORD        — (required if DATABASE_URL not set)
  CHICAGO_SOCRATA_APP_TOKEN — Optional; increases Socrata API rate limits

Prerequisites:
  pip install -r backend/requirements.txt
  # Database schema must already be applied:
  # psql $DATABASE_URL -f db/schema.sql
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Ensure the project root is on PYTHONPATH so subprocesses can resolve
# package imports like ``from backend.ingest.geocode import ...``.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
_ENV = {**os.environ, "PYTHONPATH": _PROJECT_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

STEPS = [
    {
        "name": "Fetch building permits",
        "cmd": [sys.executable, "backend/ingest/building_permits.py"],
    },
    {
        "name": "Fetch street closures",
        "cmd": [sys.executable, "backend/ingest/street_closures.py"],
    },
    {
        "name": "Fetch IDOT road construction (all districts)",
        "cmd": [sys.executable, "backend/ingest/idot_road_projects.py"],
    },
    {
        # Fetches Cook County + IL city permits from their Socrata portals.
        # Individual city failures are logged as warnings but do not abort
        # the pipeline — the step exits 0 as long as at least one city succeeds.
        "name": "Fetch IL city permits (Cook County + cities)",
        "cmd": [sys.executable, "backend/ingest/il_city_permits.py"],
        "skip_key": "skip_il_cities",
    },
    {
        # Fetches CTA planned service alerts (track work, station closures,
        # construction-related reroutes). No API key required.
        "name": "Fetch CTA planned service alerts",
        "cmd": [sys.executable, "backend/ingest/cta_alerts.py"],
        "skip_key": "skip_cta",
    },
    {
        "name": "Fill missing geocoordinates",
        "cmd": [sys.executable, "backend/ingest/geocode_fill.py"],
        "skip_key": "skip_geocode",
    },
    {
        "name": "Load projects into DB",
        "cmd": [sys.executable, "backend/ingest/load_projects.py", "--prune-days", "90"],
        "prune_args": True,
    },
]


def run_step(step: dict, args: argparse.Namespace) -> bool:
    """Run a single pipeline step. Returns True on success."""
    if step.get("skip_key") and getattr(args, step["skip_key"], False):
        print(f"\n── SKIP: {step['name']} ──────────────────────────────")
        return True

    cmd = list(step["cmd"])

    # Inject --prune-days into the load step if requested
    if step.get("prune_args") and args.prune_days is not None:
        # Replace the default --prune-days value
        try:
            idx = cmd.index("--prune-days")
            cmd[idx + 1] = str(args.prune_days)
        except ValueError:
            cmd += ["--prune-days", str(args.prune_days)]
    elif step.get("prune_args"):
        # Remove --prune-days if not requested
        try:
            idx = cmd.index("--prune-days")
            cmd.pop(idx)
            cmd.pop(idx)
        except ValueError:
            pass

    if args.dry_run and step.get("prune_args"):
        cmd.append("--dry-run")

    print(f"\n── {step['name']} ──────────────────────────────")
    print(f"   $ {' '.join(cmd)}")

    result = subprocess.run(cmd, check=False, env=_ENV)
    if result.returncode != 0:
        print(f"\nERROR: step '{step['name']}' failed with exit code {result.returncode}",
              file=sys.stderr)
        return False

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full LRE ingest pipeline against the live database."
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip the geocode_fill step (use if staging files already have coordinates).",
    )
    parser.add_argument(
        "--skip-il-cities",
        action="store_true",
        help="Skip the IL city permits fetch step (Cook County + cities).",
    )
    parser.add_argument(
        "--skip-cta",
        action="store_true",
        help="Skip the CTA planned service alerts fetch step.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data from APIs but do not write to the database.",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=90,
        metavar="N",
        help="Prune completed projects older than N days after loading (default: 90).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("══ DRY-RUN MODE: data will be fetched but not written to DB ══")

    print("══ LRE INGEST PIPELINE ═══════════════════════════════════════")

    failed: list[str] = []
    for step in STEPS:
        ok = run_step(step, args)
        if not ok:
            failed.append(step["name"])
            # Stop on failure — later steps depend on earlier outputs.
            print(f"\nPipeline aborted at step: {step['name']}", file=sys.stderr)
            break

    print("\n══ PIPELINE SUMMARY ══════════════════════════════════════════")
    if not failed:
        print("All steps completed successfully.")
        print("\nNext: verify live scoring at http://localhost:8000/score?address=<address>")
        print("      or check /health to confirm db_connection=true")
    else:
        print(f"Pipeline FAILED at: {failed[0]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
