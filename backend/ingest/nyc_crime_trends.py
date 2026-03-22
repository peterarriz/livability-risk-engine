"""
backend/ingest/nyc_crime_trends.py
task: data-044
lane: data

Ingests NYC NYPD complaint data and calculates 12-month crime trends by precinct.

Sources:
  https://data.cityofnewyork.us/resource/qgea-i56i.json
  Dataset: NYPD Complaint Data Historic (complaints from 2006 onward, updated monthly)

  https://data.cityofnewyork.us/resource/5uac-w243.json
  Dataset: NYPD Complaint Data Current Year To Date (updated daily)

  Both datasets are queried and merged to ensure full 24-month coverage.

Method:
  1. Aggregate complaint counts by precinct for the last 12 months (current window).
  2. Aggregate complaint counts by precinct for the prior 12 months (baseline).
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate precinct centroids from the average lat/lon of complaints.

Output:
  data/raw/nyc_crime_trends.json — precinct crime trend records

Usage:
  python backend/ingest/nyc_crime_trends.py
  python backend/ingest/nyc_crime_trends.py --dry-run

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

# Historic dataset — complaints from 2006 to ~3 months ago (monthly lag)
HISTORIC_URL = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
# Current YTD dataset — complaints from Jan 1 current year to ~yesterday
CURRENT_YTD_URL = "https://data.cityofnewyork.us/resource/5uac-w243.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/nyc_crime_trends.json")

# Date field and district field in the NYPD complaint datasets
DATE_FIELD = "cmplnt_fr_dt"
DISTRICT_FIELD = "addr_pct_cd"

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts_from_url(
    url: str,
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Fetch total complaint counts and approximate centroids per precinct for a date range.
    Returns dict: precinct → {count, avg_lat, avg_lon}.
    """
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count, "
            "avg(latitude) as avg_lat, "
            "avg(longitude) as avg_lon"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 200,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, dict] = {}
    for row in rows:
        precinct = str(row.get(DISTRICT_FIELD, "") or "").strip()
        if not precinct:
            continue
        try:
            # Normalize to zero-padded 3-digit string for consistent keying
            precinct = str(int(precinct))
        except (TypeError, ValueError):
            pass
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        try:
            avg_lat = float(row.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(row.get("avg_lon") or 0) or None
        except (TypeError, ValueError):
            avg_lon = None
        results[precinct] = {"count": count, "lat": avg_lat, "lon": avg_lon}

    return results


def _merge_counts(a: dict[str, dict], b: dict[str, dict]) -> dict[str, dict]:
    """
    Merge two precinct count dicts, summing counts and averaging centroids.
    Used to combine historic and YTD datasets.
    """
    merged = dict(a)
    for precinct, data in b.items():
        if precinct in merged:
            merged[precinct] = {
                "count": merged[precinct]["count"] + data["count"],
                "lat": merged[precinct]["lat"] or data["lat"],
                "lon": merged[precinct]["lon"] or data["lon"],
            }
        else:
            merged[precinct] = data
    return merged


def fetch_crime_counts_with_centroids(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """
    Query both historic and YTD datasets and merge results to cover full date range.
    """
    results: dict[str, dict] = {}

    # Try historic dataset first
    try:
        historic = fetch_crime_counts_from_url(HISTORIC_URL, app_token, start_date, end_date)
        results = _merge_counts(results, historic)
        print(f"    Historic dataset: {len(historic)} precincts.")
    except Exception as exc:
        print(f"  WARN: historic dataset query failed: {exc}", file=sys.stderr)

    # Try YTD dataset (catches recent months that may lag in historic)
    try:
        ytd = fetch_crime_counts_from_url(CURRENT_YTD_URL, app_token, start_date, end_date)
        results = _merge_counts(results, ytd)
        print(f"    YTD dataset: {len(ytd)} precincts.")
    except Exception as exc:
        print(f"  WARN: YTD dataset query failed: {exc}", file=sys.stderr)

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
    All precincts appearing in either window get a record.
    """
    all_precincts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for precinct in sorted(all_precincts, key=lambda x: int(x) if x.isdigit() else 0):
        curr = current_data.get(precinct, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(precinct, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "precinct",
            "region_id": f"nyc_precinct_{precinct}",
            "district_id": precinct,
            "district_name": f"NYPD Precinct {precinct}",
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
        "source": "nyc_crime_trends",
        "source_url": HISTORIC_URL,
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
        description="Ingest NYC NYPD crime trends by precinct from the Socrata API."
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
    print(f"  {len(current_data)} precincts with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts_with_centroids(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} precincts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} precinct trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} precincts")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
