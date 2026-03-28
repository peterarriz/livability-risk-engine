"""
backend/ingest/oakland_crime_trends.py
task: data-078
lane: data

Ingests Oakland OPD crime data and calculates 12-month crime trends by beat.

Source:
  Socrata — data.oaklandca.gov
  Dataset: OPD Crime Watch Data (not live-verified via catalog API)
  Dataset ID: ppgh-7dqv (MUST VERIFY — may be different)

  Verify dataset ID:
    curl "https://data.oaklandca.gov/api/catalog/v1?q=crime+incidents&limit=10"

  Verify sample row / field names:
    curl "https://data.oaklandca.gov/resource/ppgh-7dqv.json?$limit=1"

  Key fields (MUST VERIFY — names below are best-guess, not live-confirmed):
    datetime     — date of incident  (MUST VERIFY field name)
    beat         — patrol beat/area  (MUST VERIFY — may be "district")
    lat          — latitude          (MUST VERIFY)
    long_        — longitude         (MUST VERIFY — Socrata uses "long_" to avoid
                                      the SQL reserved word "long"; may be "lon"
                                      or "longitude")

  NOTE: CI has no outbound HTTPS.  All field/dataset verification must be done
  manually (task data-079) using the curl commands above before this script is
  used in production.

Method:
  1. Aggregate crime counts by beat for the last 12 months (current window).
  2. Aggregate crime counts by beat for the prior 12 months (baseline).
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate beat centroids from the average lat/lon of incidents.

Output:
  data/raw/oakland_crime_trends.json — beat crime trend records

Usage:
  python backend/ingest/oakland_crime_trends.py
  python backend/ingest/oakland_crime_trends.py --dry-run

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
                       Register free at https://dev.socrata.com/register
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

SOCRATA_DOMAIN = "data.oaklandca.gov"
DATASET_ID = "ppgh-7dqv"   # MUST VERIFY — not live-confirmed
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/oakland_crime_trends.json")

# Date field and district field in the Oakland OPD crime dataset.
# MUST VERIFY field names against the actual dataset before production use.
DATE_FIELD = "datetime"         # MUST VERIFY — may differ
DISTRICT_FIELD = "beat"         # MUST VERIFY — may be "district" or "reporting_area"
LAT_FIELD = "lat"               # MUST VERIFY
LON_FIELD = "long_"             # MUST VERIFY — Socrata sometimes uses "long_" to avoid
                                #               the SQL reserved word "long"

# City centre fallback (unused in computation; reserved for future use)
OAKLAND_LAT = 37.8044
OAKLAND_LON = -122.2711

# Changes within ±5 % are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts_with_centroids(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total crime counts per beat for a date range, with avg lat/lon.
    Uses SoQL GROUP BY to compute aggregates server-side.

    Returns dict: beat → {count, lat, lon}.

    MUST VERIFY: DATE_FIELD, DISTRICT_FIELD, LAT_FIELD, LON_FIELD, and
    DATASET_ID against data.oaklandca.gov before production use.
    CI has no outbound HTTPS — verify manually with:
      curl "https://data.oaklandca.gov/resource/ppgh-7dqv.json?$limit=1"
    """
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count, "
            f"avg({LAT_FIELD}::number) as avg_lat, "
            f"avg({LON_FIELD}::number) as avg_lon"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 100,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, dict] = {}
    for row in rows:
        beat = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not beat:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        try:
            lat = float(row["avg_lat"]) if row.get("avg_lat") is not None else None
        except (TypeError, ValueError):
            lat = None
        try:
            lon = float(row["avg_lon"]) if row.get("avg_lon") is not None else None
        except (TypeError, ValueError):
            lon = None
        results[beat] = {"count": count, "lat": lat, "lon": lon}

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
    All beats appearing in either window get a record.
    Centroid coordinates are taken from the current window; fallback to prior.
    """
    all_beats = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for beat in sorted(all_beats):
        curr = current_data.get(beat, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(beat, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "beat",
            "region_id": f"oakland_beat_{beat}",
            "district_id": beat,
            "district_name": f"Oakland Beat {beat}",
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
        "source": "oakland_crime_trends",
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
        description="Ingest Oakland OPD crime trends by beat from the Socrata API."
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
        current_data = fetch_crime_counts_with_centroids(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} beats with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} beats with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} beat trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} beats")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
