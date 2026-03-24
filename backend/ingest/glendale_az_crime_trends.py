"""
backend/ingest/glendale_az_crime_trends.py
task: data-058
lane: data

Ingests Glendale, AZ Police Department (GPD) crime data and calculates
12-month crime trends by beat.

NOTE: This is Glendale, AZ (Maricopa County), not Glendale, CA.

Source:
  ArcGIS FeatureServer — Glendale AZ Open Data (ArcGIS Hub)
  Portal: https://glendaleaz-cog-gis.hub.arcgis.com/
  Service: GPD CRIME DATA REDACTED (Table ID 2)
  Item: https://www.arcgis.com/home/item.html?id=2565b89bed184a89aa0300c85fe14c43

  Key fields:
    Occurred_On_Date — date of incident
    BEAT_GIS         — beat (geographic grouping)

Output:
  data/raw/glendale_az_crime_trends.json

Usage:
  python backend/ingest/glendale_az_crime_trends.py
  python backend/ingest/glendale_az_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

FEATURESERVER_URL = (
    "https://services1.arcgis.com/9fVTQQSiODPjLUTa/arcgis/rest/services"
    "/GPD_CRIME_DATA_REDACTED/FeatureServer/2"
)

DEFAULT_OUTPUT_PATH = Path("data/raw/glendale_az_crime_trends.json")

DATE_FIELD = "Occurred_On_Date"
GROUP_FIELD = "BEAT_GIS"

GLENDALE_AZ_LAT = 33.5387
GLENDALE_AZ_LON = -112.1860

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    """Return date string for ArcGIS date queries (single-quoted)."""
    return f"'{dt.strftime('%Y-%m-%d')}'"


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = f"{FEATURESERVER_URL}/query"

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
        count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
        results[beat] = results.get(beat, 0) + count
    return results


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
        slug = beat.lower().replace(" ", "_")
        records.append({
            "region_type": "beat",
            "region_id": f"glendale_az_beat_{slug}",
            "beat_id": beat,
            "beat_name": f"Glendale AZ Beat {beat}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": GLENDALE_AZ_LAT,
            "longitude": GLENDALE_AZ_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "glendale_az_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Glendale AZ GPD crime trends by district from ArcGIS FeatureServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Glendale AZ crime trends ingest — GPD CRIME DATA REDACTED (FeatureServer/2)")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Glendale AZ crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} beats, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Glendale AZ crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} beats, {total_prior:,} total crimes.")

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
