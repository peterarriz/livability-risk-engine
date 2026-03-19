"""
backend/ingest/db_summary.py
task: data-016
lane: data

Lightweight read-only diagnostic that queries the canonical `projects`
table and prints a concise summary of record counts by source, status,
and impact_type, plus freshness information per source.

Output is designed to be copy-paste-ready so Data can share it with
App as a QA artifact after each successful live-data load.

Usage:
  # Human-readable output (default):
  python backend/ingest/db_summary.py

  # Machine-readable JSON:
  python backend/ingest/db_summary.py --json

Environment variables (required):
  POSTGRES_HOST      (default: localhost)
  POSTGRES_PORT      (default: 5432)
  POSTGRES_DB        (default: livability)
  POSTGRES_USER      (default: postgres)
  POSTGRES_PASSWORD  (required)

Acceptance criteria (data-016):
  - Queries projects table and prints counts by source, status,
    and impact_type.
  - Shows the freshest and oldest normalized_at per source so
    Data can confirm a successful load.
  - Exits 0 always; output is copy-paste-ready for App QA.
  - Works with the same POSTGRES_* env vars as load_projects.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

TOTAL_BY_SOURCE_STATUS = """
SELECT source, status, COUNT(*) AS cnt
FROM projects
GROUP BY source, status
ORDER BY source, status;
"""

TOTAL_BY_SOURCE_IMPACT = """
SELECT source, impact_type, COUNT(*) AS cnt
FROM projects
GROUP BY source, impact_type
ORDER BY source, impact_type;
"""

FRESHNESS_BY_SOURCE = """
SELECT
    source,
    COUNT(*)                              AS total,
    MAX(normalized_at)                    AS newest_normalized_at,
    MIN(normalized_at)                    AS oldest_normalized_at,
    COUNT(*) FILTER (WHERE geom IS NULL)  AS missing_geom
FROM projects
GROUP BY source
ORDER BY source;
"""

ACTIVE_PLANNED_SCOREABLE = """
SELECT COUNT(*) AS scoreable
FROM projects
WHERE status IN ('active', 'planned', 'unknown')
  AND geom IS NOT NULL;
"""


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def get_db_connection():
    if not HAS_PSYCOPG2:
        raise ImportError("psycopg2 is required. pip install psycopg2-binary")
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "livability"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _run(conn, sql: str) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Report formatters
# ---------------------------------------------------------------------------

def _fmt_ts(ts) -> str:
    if ts is None:
        return "—"
    if hasattr(ts, "isoformat"):
        return ts.isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(ts)


def print_report(conn) -> dict:
    """Run all queries and print a human-readable report. Returns data dict."""
    by_source_status = _run(conn, TOTAL_BY_SOURCE_STATUS)
    by_source_impact = _run(conn, TOTAL_BY_SOURCE_IMPACT)
    freshness        = _run(conn, FRESHNESS_BY_SOURCE)
    scoreable_rows   = _run(conn, ACTIVE_PLANNED_SCOREABLE)
    scoreable        = scoreable_rows[0]["scoreable"] if scoreable_rows else 0

    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    print(f"\n══ DB SUMMARY — {now_str} ═══════════════════════════")

    # ── Scoreable record count ──
    print(f"\n  Scoreable records (active/planned/unknown + geom): {scoreable}")

    # ── By source and status ──
    print("\n  ── Records by source + status ──────────────────────")
    prev_source = None
    for row in by_source_status:
        if row["source"] != prev_source:
            print(f"  {row['source']}")
            prev_source = row["source"]
        print(f"    {row['status']:<12}  {row['cnt']:>6}")

    # ── By source and impact_type ──
    print("\n  ── Records by source + impact_type ─────────────────")
    prev_source = None
    for row in by_source_impact:
        if row["source"] != prev_source:
            print(f"  {row['source']}")
            prev_source = row["source"]
        print(f"    {row['impact_type']:<22}  {row['cnt']:>6}")

    # ── Freshness ──
    print("\n  ── Freshness by source ──────────────────────────────")
    for row in freshness:
        print(f"  {row['source']}")
        print(f"    Total rows:        {row['total']}")
        print(f"    Newest load:       {_fmt_ts(row['newest_normalized_at'])}")
        print(f"    Oldest load:       {_fmt_ts(row['oldest_normalized_at'])}")
        print(f"    Missing geom:      {row['missing_geom']}")

    print()

    return {
        "generated_at": now_str,
        "scoreable": scoreable,
        "by_source_status": by_source_status,
        "by_source_impact": by_source_impact,
        "freshness": [
            {**row, "newest_normalized_at": _fmt_ts(row["newest_normalized_at"]),
             "oldest_normalized_at": _fmt_ts(row["oldest_normalized_at"])}
            for row in freshness
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a read-only summary of the canonical projects table."
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output results as JSON instead of human-readable text.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not HAS_PSYCOPG2:
        print("ERROR: psycopg2 is required. pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    try:
        conn = get_db_connection()
    except Exception as exc:
        print(f"ERROR: could not connect to DB — {exc}", file=sys.stderr)
        print(
            "Tip: set POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = print_report(conn)
    finally:
        conn.close()

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
