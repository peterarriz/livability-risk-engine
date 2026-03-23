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
from typing import Optional

# Ensure the project root is on PYTHONPATH so subprocesses can resolve
# package imports like ``from backend.ingest.geocode import ...``.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
_ENV = {**os.environ, "PYTHONPATH": _PROJECT_ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

STEPS = [
    {
        "name": "Fetch Chicago building permits",
        "cmd": [sys.executable, "backend/ingest/building_permits.py"],
    },
    {
        "name": "Fetch Chicago street closures",
        "cmd": [sys.executable, "backend/ingest/street_closures.py"],
    },
    {
        "name": "Fetch IDOT road construction (all districts)",
        "cmd": [sys.executable, "backend/ingest/idot_road_projects.py"],
        "skip_key": "skip_statewide",
    },
    # Cook County permits are handled by il_city_permits.py (dataset 6yjf-dfxs).
    # The standalone cook_county_permits.py has an incorrect dataset ID and is
    # skipped to avoid pipeline failures. Remove this comment when the
    # standalone script is fixed or deleted.
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
        # Fetches recent Chicago traffic crashes (last 30 days).
        # Recent crash scenes are disruption signals. Dataset: 85ca-t3if.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago traffic crashes",
        "cmd": [sys.executable, "backend/ingest/chicago_traffic_crashes.py"],
        "skip_key": "skip_traffic_crashes",
        "non_fatal": True,
    },
    {
        # Fetches Divvy bike station closures via GBFS API.
        # Out-of-service stations are LOW-severity disruption signals.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Divvy bike station closures",
        "cmd": [sys.executable, "backend/ingest/chicago_divvy_stations.py"],
        "skip_key": "skip_divvy",
        "non_fatal": True,
    },
    {
        # Fetches Chicago 311 infrastructure service requests:
        # potholes, water main breaks, cave-ins, tree emergencies.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago 311 infrastructure requests",
        "cmd": [sys.executable, "backend/ingest/chicago_311_requests.py"],
        "skip_key": "skip_311",
        "non_fatal": True,
    },
    {
        # Fetches Chicago Film Permits (DCASE).
        # Film shoots cause street closures and parking restrictions.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago film permits",
        "cmd": [sys.executable, "backend/ingest/chicago_film_permits.py"],
        "skip_key": "skip_film",
        "non_fatal": True,
    },
    {
        # Fetches Chicago Special Events Permits (DCASE).
        # Festivals, parades, and marathons cause major traffic disruption.
        # Failures are non-fatal — pipeline continues to next step.
        "name": "Fetch Chicago special events permits",
        "cmd": [sys.executable, "backend/ingest/chicago_special_events.py"],
        "skip_key": "skip_events",
        "non_fatal": True,
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


# ---------------------------------------------------------------------------
# Ingest run tracking  (data-041)
# Writes to the ingest_runs table so /health/db can report freshness and
# so the regression check can compare current vs prior record counts.
# All DB calls are best-effort — failures are logged but never abort the pipeline.
# ---------------------------------------------------------------------------

def _get_db_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or None


def _record_run_start(db_url: str) -> Optional[int]:
    """Insert a 'running' row into ingest_runs. Returns the new row ID."""
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingest_runs (source, status) VALUES (%s, %s) RETURNING id",
                ("pipeline", "running"),
            )
            row_id = cur.fetchone()[0]
        conn.close()
        return row_id
    except Exception as exc:
        print(f"WARN: could not record ingest run start: {exc}", file=sys.stderr)
        return None


def _check_regression_and_finish(
    db_url: str, run_id: Optional[int], failed_step: Optional[str]
) -> None:
    """
    Query active project count, compare against the previous successful run,
    then write the final status to ingest_runs.

    Exits with code 1 if:
      - a pipeline step already failed (failed_step is set), OR
      - active project count dropped >20% compared to the prior run.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, connect_timeout=5)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            current_count: int = cur.fetchone()[0]

            # Last *finished* successful run (the current run is still 'running')
            cur.execute(
                """SELECT record_count FROM ingest_runs
                   WHERE status = 'success' AND record_count IS NOT NULL
                   ORDER BY finished_at DESC LIMIT 1"""
            )
            prior_row = cur.fetchone()

        regression_error: Optional[str] = None
        if prior_row is not None:
            prior_count: int = prior_row[0]
            if prior_count > 0:
                drop_pct = (prior_count - current_count) / prior_count * 100
                if drop_pct > 20:
                    regression_error = (
                        f"Active project count dropped {drop_pct:.1f}% "
                        f"(was {prior_count}, now {current_count}). "
                        f">20% regression threshold exceeded."
                    )
                    print(f"ERROR: {regression_error}", file=sys.stderr)
                elif drop_pct > 0:
                    print(
                        f"Row count: {current_count} active projects "
                        f"(down {drop_pct:.1f}% from {prior_count} — within 20% threshold)."
                    )
                else:
                    print(
                        f"Row count: {current_count} active projects "
                        f"(up from {prior_count})."
                    )
            else:
                print(f"Row count: {current_count} active projects.")
        else:
            print(f"Row count: {current_count} active projects (no prior run to compare).")

        # Determine final status
        if failed_step:
            final_status = "failed"
            error_msg = f"Pipeline aborted at step: {failed_step}"
        elif regression_error:
            final_status = "failed"
            error_msg = regression_error
        else:
            final_status = "success"
            error_msg = None

        # Write final row
        with conn.cursor() as cur:
            if run_id is not None:
                cur.execute(
                    """UPDATE ingest_runs
                       SET finished_at = now(), status = %s, record_count = %s, error_msg = %s
                       WHERE id = %s""",
                    (final_status, current_count, error_msg, run_id),
                )
            else:
                cur.execute(
                    """INSERT INTO ingest_runs (source, finished_at, status, record_count, error_msg)
                       VALUES (%s, now(), %s, %s, %s)""",
                    ("pipeline", final_status, current_count, error_msg),
                )
        conn.close()

        if final_status == "failed":
            sys.exit(1)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"WARN: could not record ingest run finish: {exc}", file=sys.stderr)
        # Still exit 1 if a step failed
        if failed_step:
            sys.exit(1)


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
        if step.get("non_fatal"):
            print(
                f"\nWARN: step '{step['name']}' failed with exit code {result.returncode}. "
                f"This step is non-fatal — continuing pipeline.",
                file=sys.stderr,
            )
            return True  # non-fatal: don't abort pipeline
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
        "--skip-traffic-crashes",
        action="store_true",
        help="Skip the Chicago traffic crashes fetch step.",
    )
    parser.add_argument(
        "--skip-divvy",
        action="store_true",
        help="Skip the Divvy bike station closures fetch step.",
    )
    parser.add_argument(
        "--skip-311",
        action="store_true",
        help="Skip the Chicago 311 infrastructure requests fetch step.",
    )
    parser.add_argument(
        "--skip-film",
        action="store_true",
        help="Skip the Chicago film permits fetch step.",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="Skip the Chicago special events permits fetch step.",
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

    # Record pipeline start in ingest_runs (best-effort; skipped on dry-run)
    db_url = _get_db_url()
    run_id: Optional[int] = None
    if db_url and not args.dry_run:
        run_id = _record_run_start(db_url)

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

    # Record final status + regression check (best-effort; skipped on dry-run)
    if db_url and not args.dry_run:
        _check_regression_and_finish(
            db_url,
            run_id,
            failed_step=failed[0] if failed else None,
        )
    elif failed:
        print(f"Pipeline FAILED at: {failed[0]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
