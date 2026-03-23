"""
scripts/validate_ingest.py
task: data-044
lane: data

Post-ingest data quality validation.

Runs four checks against the live `projects` table and exits 1 if any
hard threshold is breached, causing the GitHub Actions ingest job to fail
and trigger the failure notification wired in data-041.

Checks:
  1. Missing coordinates  — active records with no lat/lon (threshold: >5%)
  2. Stale active records — status='active' but end_date >30 days in the past
                           (threshold: >10% of active records)
  3. Duplicate source IDs — duplicate (source, source_id) pairs indicating
                            the upsert ON CONFLICT is not matching correctly
                           (threshold: any duplicates)
  4. Unknown impact types — impact_type values not in the scoring weight map;
                            these fall back to light_permit weight silently
                           (threshold: any unknown types)

Usage:
  DATABASE_URL="postgres://..." python scripts/validate_ingest.py

Exit codes:
  0 — all checks passed (warnings are printed but do not fail)
  1 — one or more hard thresholds breached
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow imports from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

KNOWN_IMPACT_TYPES = {
    "closure_full",
    "closure_multi_lane",
    "closure_single_lane",
    "demolition",
    "construction",
    "road_construction",
    "light_permit",
}

# Hard-failure thresholds
MISSING_COORDS_THRESHOLD_PCT = 5.0   # >5% active records missing lat/lon
STALE_ACTIVE_THRESHOLD_PCT   = 10.0  # >10% active records with end_date >30 days past


def get_db_connection():
    import psycopg2
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url, connect_timeout=10)
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "livability"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=10,
    )


def run_checks() -> list[str]:
    """
    Run all four checks. Returns a list of failure messages.
    An empty list means all checks passed.
    """
    failures: list[str] = []
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:

            # ------------------------------------------------------------------
            # Check 1: Missing coordinates
            # ------------------------------------------------------------------
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            total_active: int = cur.fetchone()[0]

            cur.execute(
                """SELECT COUNT(*) FROM projects
                   WHERE status = 'active'
                     AND (latitude IS NULL OR longitude IS NULL)"""
            )
            missing_coords: int = cur.fetchone()[0]

            if total_active == 0:
                print("CHECK 1 — Missing coordinates: SKIP (no active records)")
            else:
                pct = missing_coords / total_active * 100
                if pct > MISSING_COORDS_THRESHOLD_PCT:
                    msg = (
                        f"CHECK 1 — Missing coordinates: FAIL "
                        f"({missing_coords}/{total_active} active records = {pct:.1f}% "
                        f"missing lat/lon, threshold {MISSING_COORDS_THRESHOLD_PCT}%)"
                    )
                    print(msg)
                    failures.append(msg)
                elif missing_coords > 0:
                    print(
                        f"CHECK 1 — Missing coordinates: WARN "
                        f"({missing_coords}/{total_active} = {pct:.1f}% missing lat/lon, "
                        f"within {MISSING_COORDS_THRESHOLD_PCT}% threshold)"
                    )
                else:
                    print(f"CHECK 1 — Missing coordinates: OK (0/{total_active})")

            # ------------------------------------------------------------------
            # Check 2: Stale active records
            # ------------------------------------------------------------------
            cur.execute(
                """SELECT COUNT(*) FROM projects
                   WHERE status = 'active'
                     AND end_date IS NOT NULL
                     AND end_date < NOW() - INTERVAL '30 days'"""
            )
            stale_count: int = cur.fetchone()[0]

            if total_active == 0:
                print("CHECK 2 — Stale active records: SKIP (no active records)")
            else:
                pct = stale_count / total_active * 100
                if pct > STALE_ACTIVE_THRESHOLD_PCT:
                    msg = (
                        f"CHECK 2 — Stale active records: FAIL "
                        f"({stale_count}/{total_active} active records = {pct:.1f}% "
                        f"have end_date >30 days past, threshold {STALE_ACTIVE_THRESHOLD_PCT}%)"
                    )
                    print(msg)
                    failures.append(msg)
                elif stale_count > 0:
                    print(
                        f"CHECK 2 — Stale active records: WARN "
                        f"({stale_count}/{total_active} = {pct:.1f}% stale, "
                        f"within {STALE_ACTIVE_THRESHOLD_PCT}% threshold)"
                    )
                else:
                    print(f"CHECK 2 — Stale active records: OK (0/{total_active})")

            # ------------------------------------------------------------------
            # Check 3: Duplicate source IDs
            # ------------------------------------------------------------------
            cur.execute(
                """SELECT source, COUNT(*) AS total, COUNT(DISTINCT source_id) AS unique_ids
                   FROM projects
                   GROUP BY source
                   HAVING COUNT(*) != COUNT(DISTINCT source_id)"""
            )
            dup_rows = cur.fetchall()

            if dup_rows:
                for source, total, unique_ids in dup_rows:
                    dups = total - unique_ids
                    msg = (
                        f"CHECK 3 — Duplicate source IDs: FAIL "
                        f"(source='{source}': {dups} duplicate source_id(s) — "
                        f"ON CONFLICT upsert may not be matching correctly)"
                    )
                    print(msg)
                    failures.append(msg)
            else:
                print("CHECK 3 — Duplicate source IDs: OK")

            # ------------------------------------------------------------------
            # Check 4: Unknown impact types
            # ------------------------------------------------------------------
            placeholders = ",".join(["%s"] * len(KNOWN_IMPACT_TYPES))
            cur.execute(
                f"""SELECT impact_type, COUNT(*) AS cnt
                    FROM projects
                    WHERE impact_type NOT IN ({placeholders})
                    GROUP BY impact_type
                    ORDER BY cnt DESC""",
                tuple(KNOWN_IMPACT_TYPES),
            )
            unknown_rows = cur.fetchall()

            if unknown_rows:
                for impact_type, cnt in unknown_rows:
                    msg = (
                        f"CHECK 4 — Unknown impact type: FAIL "
                        f"(impact_type='{impact_type}' found {cnt} time(s) — "
                        f"not in scoring weight map, falls back to light_permit silently)"
                    )
                    print(msg)
                    failures.append(msg)
            else:
                print("CHECK 4 — Unknown impact types: OK")

    finally:
        conn.close()

    return failures


def main() -> None:
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST")
    if not db_url:
        print("ERROR: DATABASE_URL (or POSTGRES_HOST) not set — cannot run validation")
        sys.exit(1)

    print("══ INGEST DATA QUALITY VALIDATION ════════════════════════════")
    try:
        failures = run_checks()
    except Exception as exc:
        print(f"ERROR: validation script failed unexpectedly: {exc}")
        sys.exit(1)

    print("══ VALIDATION SUMMARY ════════════════════════════════════════")
    if not failures:
        print("All checks passed.")
    else:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  • {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
