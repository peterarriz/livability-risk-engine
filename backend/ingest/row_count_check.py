"""
backend/ingest/row_count_check.py
task: data-041
lane: data

Row-count regression check for the ingest pipeline.

Compares the current active project count in the `projects` table against the
record_count stored in the most recent successful `ingest_runs` row. If the
count has dropped by more than REGRESSION_THRESHOLD (default 20%), exits
non-zero so the CI step fails and surfaces the anomaly before users notice
stale data.

Usage:
  python backend/ingest/row_count_check.py

  # Custom threshold:
  python backend/ingest/row_count_check.py --threshold 0.15

Environment variables:
  DATABASE_URL  — Railway Postgres connection string (required)

Exit codes:
  0  Count is within acceptable range (or no prior run to compare against).
  1  Count dropped more than REGRESSION_THRESHOLD vs prior successful run.
  2  DB connection failed or required env var missing.
"""

from __future__ import annotations

import argparse
import os
import sys

DEFAULT_THRESHOLD = 0.20  # 20% drop triggers alert


def get_db_connection():
    import psycopg2

    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    db = os.environ.get("POSTGRES_DB", "livability")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=password)


def run_check(threshold: float) -> int:
    """
    Returns 0 if count is healthy, 1 if regression detected, 2 on error.
    """
    try:
        conn = get_db_connection()
    except Exception as exc:
        print(f"ERROR: Could not connect to DB: {exc}", file=sys.stderr)
        return 2

    try:
        with conn.cursor() as cur:
            # Current active project count
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            current_count: int = cur.fetchone()[0]

            # Most recent successful ingest run's recorded count (all sources combined)
            cur.execute(
                """
                SELECT SUM(record_count)
                FROM ingest_runs
                WHERE status = 'success'
                  AND finished_at = (
                      SELECT MAX(finished_at)
                      FROM ingest_runs
                      WHERE status = 'success'
                        AND record_count IS NOT NULL
                  )
                """
            )
            row = cur.fetchone()
            prior_count = row[0] if row and row[0] is not None else None
    except Exception as exc:
        print(f"ERROR: Query failed: {exc}", file=sys.stderr)
        conn.close()
        return 2
    finally:
        conn.close()

    print(f"Current active project count : {current_count:,}")

    if prior_count is None:
        print("No prior successful ingest run found — skipping regression check.")
        return 0

    print(f"Prior ingest recorded count  : {prior_count:,}")

    if prior_count == 0:
        print("Prior count was zero — skipping regression check.")
        return 0

    drop_pct = (prior_count - current_count) / prior_count
    threshold_pct = int(threshold * 100)

    if drop_pct > threshold:
        print(
            f"REGRESSION DETECTED: active project count dropped {drop_pct:.1%} "
            f"vs prior run (threshold: {threshold_pct}%). "
            f"Was {prior_count:,}, now {current_count:,}.",
            file=sys.stderr,
        )
        print(
            "Possible causes: ingest failure, mass record expiry, or source data issue.",
            file=sys.stderr,
        )
        return 1

    if drop_pct > 0:
        print(f"Count dropped {drop_pct:.1%} vs prior run — within {threshold_pct}% threshold. OK.")
    else:
        print(f"Count is stable or grew vs prior run. OK.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check active project count hasn't regressed more than a threshold."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        metavar="FRACTION",
        help=f"Fraction drop that triggers alert (default: {DEFAULT_THRESHOLD} = 20%%).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST")
    if not db_url:
        print(
            "ERROR: DATABASE_URL or POSTGRES_HOST environment variable not set. "
            "Row-count check requires a live DB connection.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("\n── Row-count regression check ───────────────────────")
    exit_code = run_check(args.threshold)
    print()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
