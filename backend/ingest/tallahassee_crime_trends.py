"""
backend/ingest/tallahassee_crime_trends.py
task: data-068
lane: data

Ingests Tallahassee Police Department crime data and calculates
12-month crime trends by beat.

Source:
  ArcGIS MapServer — TOPS (Tallahassee Online Police Statistics)
  Hosted by Leon County GIS at cotinter.leoncountyfl.gov

  Verified service URL:
    https://cotinter.leoncountyfl.gov/cotinter/rest/services/Vector
    /COT_InterTOPS_D_WM/MapServer/2

  Layer 2 = "Crime Incidents 365 Days" (rolling window, ~160k records)
  Note: only ~365 days of data available. Prior-year comparison will be
  sparse or empty. Trend classification should be treated as current-only.

  Key fields (verified via sample query):
    INCIDENT_TIME_ADJ — date of incident (esriFieldTypeDate, epoch ms)
    BEAT              — TPD beat (NE1-NE6, NW1-NW2, SE1-SE3, SW1-SW3, etc.)
    DISPO_TEXT        — crime/incident type (ASSAULT, BURGLARY, etc.)

Output:
  data/raw/tallahassee_crime_trends.json — beat crime trend records

Usage:
  python backend/ingest/tallahassee_crime_trends.py
  python backend/ingest/tallahassee_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Verified: TOPS MapServer Layer 2 on Leon County GIS
MAPSERVER_URL = (
    "https://cotinter.leoncountyfl.gov/cotinter/rest/services/Vector"
    "/COT_InterTOPS_D_WM/MapServer/2"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/tallahassee_crime_trends.json")

# Verified field names
DATE_FIELD = "INCIDENT_TIME_ADJ"
GROUP_FIELD = "BEAT"

TALLAHASSEE_LAT = 30.4518
TALLAHASSEE_LON = -84.2807

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = f"{MAPSERVER_URL}/query"

    where_clause = (
        f"{DATE_FIELD} >= {_date_str(start_date)} "
        f"AND {DATE_FIELD} < {_date_str(end_date)}"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
    ])

    params = {
        "where": where_clause,
        "groupByFieldsForStatistics": GROUP_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(url, data=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(f"ArcGIS query error: {payload['error']}")

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        beat = str(attrs.get(GROUP_FIELD) or "").strip()
        if not beat:
            continue
        count = int(attrs.get("crime_count", 0) or attrs.get("CRIME_COUNT", 0))
        results[beat] = results.get(beat, 0) + count
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
        slug = beat.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "beat",
            "region_id": f"tallahassee_beat_{slug}",
            "district_id": beat,
            "district_name": f"Tallahassee Beat {beat}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": TALLAHASSEE_LAT,
            "longitude": TALLAHASSEE_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "tallahassee_crime_trends",
        "source_url": MAPSERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Tallahassee TPD crime trends by beat from ArcGIS MapServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Tallahassee crime trends ingest — source: {MAPSERVER_URL}")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"\nFetching current 12-month counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} beats, {sum(current_data.values()):,} total crimes.")

    print(f"\nFetching prior 12-month counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} beats, {sum(prior_data.values()):,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} beat trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} beats")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
