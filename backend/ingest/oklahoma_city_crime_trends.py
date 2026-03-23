"""
backend/ingest/oklahoma_city_crime_trends.py
task: data-049
lane: data

Ingests Oklahoma City Police Department crime data and calculates 12-month
crime trends by district/beat.

Source:
  https://data.okc.gov/resource/f972-d93c.json
  Dataset: "Police Incidents" (OKCPD)

  Verify dataset_id:
    curl "https://data.okc.gov/api/catalog/v1?q=police+incidents&limit=5"
    curl "https://data.okc.gov/resource/f972-d93c.json?$limit=1"

Output:
  data/raw/oklahoma_city_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/oklahoma_city_crime_trends.py
  python backend/ingest/oklahoma_city_crime_trends.py --dry-run
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

CRIMES_URL = "https://data.okc.gov/resource/f972-d93c.json"
SOCRATA_DOMAIN = "data.okc.gov"

DEFAULT_OUTPUT_PATH = Path("data/raw/oklahoma_city_crime_trends.json")

DATE_FIELD = "date_reported"
DISTRICT_FIELD = "beat"

STABLE_THRESHOLD_PCT = 5.0

# City center fallback
OKC_LAT = 35.4676
OKC_LON = -97.5164


# ---------------------------------------------------------------------------
# Crime aggregate queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Aggregate crime counts per beat via SoQL GROUP BY."""
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": f"{DISTRICT_FIELD}, count(*) as crime_count",
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 500,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, int] = {}
    for row in rows:
        beat = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not beat:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        results[beat] = count

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
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    all_beats = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for beat in sorted(all_beats):
        current_count = current_data.get(beat, 0)
        prior_count = prior_data.get(beat, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "beat",
            "region_id": f"okc_beat_{beat}",
            "district_id": beat,
            "district_name": f"Oklahoma City Beat {beat}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": OKC_LAT,
            "longitude": OKC_LON,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "oklahoma_city_crime_trends",
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
        description="Ingest Oklahoma City crime trends by beat from the Socrata API."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    if not app_token:
        print("Note: SOCRATA_APP_TOKEN not set. Requests will be rate-limited.")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month crime counts ({_date_str(current_start)} → {_date_str(now)})...")
    try:
        current_data = fetch_crime_counts(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} beats with current crime data.")

    print(f"\nFetching prior 12-month crime counts ({_date_str(prior_start)} → {_date_str(prior_end)})...")
    try:
        prior_data = fetch_crime_counts(app_token, prior_start, prior_end)
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
