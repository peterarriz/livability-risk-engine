"""
backend/ingest/kansas_city_crime_trends.py
task: data-045
lane: data

Ingests Kansas City KCPD crime data and calculates 12-month crime trends by division.

Source:
  https://data.kcmo.org/resource/kagq-28me.json
  Dataset: KCPD Crime Data (Kansas City Police Department)

  Verify dataset_id:
    curl "https://data.kcmo.org/api/catalog/v1?q=crime&limit=5"
  Sample first record to confirm field names:
    curl "https://data.kcmo.org/resource/kagq-28me.json?$limit=1"

Method:
  1. Aggregate crime counts by division for the last 12 months (current window).
  2. Aggregate crime counts by division for the prior 12 months (baseline).
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/kansas_city_crime_trends.json — division crime trend records

Usage:
  python backend/ingest/kansas_city_crime_trends.py
  python backend/ingest/kansas_city_crime_trends.py --dry-run

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Verify this dataset_id:
#   curl "https://data.kcmo.org/api/catalog/v1?q=crime&limit=5"
CRIMES_URL = "https://data.kcmo.org/resource/kagq-28me.json"
SOCRATA_DOMAIN = "data.kcmo.org"

DEFAULT_OUTPUT_PATH = Path("data/raw/kansas_city_crime_trends.json")

# Date field and district field in the KCPD crime dataset.
# Verify by sampling: curl "https://data.kcmo.org/resource/kagq-28me.json?$limit=1"
# Known KCPD crime dataset fields (2026 schema):
#   "report_no", "reported_date", "from_date", "to_date", "description",
#   "ibrs", "address", "city", "zip_code", "rep_dist_num", "involvement",
#   "race", "sex", "age", "firearm_used_flag", "location", "x", "y"
# Common date field alternatives: "reported_date" (confirmed), "from_date"
DATE_FIELD = "reported_date"
# Common district field alternatives: "rep_dist_num" (reporting district number),
# "patrol_division" (if grouped by division), "beat"
# Note: KCPD data may not have a "division" field — "rep_dist_num" is more common.
# If this script returns 0 divisions, try DISTRICT_FIELD = "rep_dist_num".
DISTRICT_FIELD = "division"

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total crime counts per division for a date range.
    Uses SoQL GROUP BY to compute counts server-side.
    Returns dict: division → {count, lat (None), lon (None)}.
    """
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 200,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, dict] = {}
    for row in rows:
        division = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not division:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        results[division] = {"count": count, "lat": None, "lon": None}

    return results


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def _classify_trend(current: int, prior: int) -> tuple[str, float]:
    if prior == 0:
        if current > 0:
            return "INCREASING", 100.0
        return "STABLE", 0.0

    pct = (current - prior) / prior * 100.0
    if pct >= STABLE_THRESHOLD_PCT:
        return "INCREASING", round(pct, 1)
    if pct <= -STABLE_THRESHOLD_PCT:
        return "DECREASING", round(pct, 1)
    return "STABLE", round(pct, 1)


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------

def build_trend_records(
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    All divisions appearing in either window get a record.
    """
    all_divisions = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for division in sorted(all_divisions):
        curr = current_data.get(division, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(division, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "division",
            "region_id": f"kansas_city_division_{division}",
            "district_id": division,
            "district_name": f"Kansas City Division {division}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat,
            "longitude": lon,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "kansas_city_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Kansas City KCPD crime trends by division from the Socrata API."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if not app_token:
        print(
            "Note: SOCRATA_APP_TOKEN not set. "
            "Requests will be rate-limited. "
            "Register free at https://dev.socrata.com/register"
        )

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month crime counts ({_date_str(current_start)} → {_date_str(now)})...")
    try:
        current_data = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        print(
            f"  Verify dataset_id by running:\n"
            f"  curl 'https://{SOCRATA_DOMAIN}/api/catalog/v1?q=crime&limit=5'",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"  {len(current_data)} divisions with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} divisions with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} division trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} divisions")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
