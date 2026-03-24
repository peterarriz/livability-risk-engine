"""
backend/ingest/henderson_crime_trends.py
task: data-058
lane: data

Ingests Henderson Police Department (HPD) crime data and calculates
12-month crime trends by beat.

NOTE: Henderson, NV has its own police department (HPD), separate from
the Las Vegas Metropolitan Police Department (LVMPD). Henderson is not
covered by the existing las_vegas_crime_trends.py script.

Source:
  ArcGIS MapServer — City of Henderson Open Data (Public Safety)
  Portal: https://gis-hendersonnv.opendata.arcgis.com/
  Service: https://maps.cityofhenderson.com/arcgis/rest/services/public/OpenDataPublicSafety/MapServer
  Layers:
    5  — Daily Crime Data (rolling ~90 days, includes most recent data)
    6  — Crime Data 2014
    ...
    17 — Crime Data 2025
  Fields (same across all crime layers):
    OCCURRED_S — date of incident (start)
    BEAT       — police beat (geographic grouping, e.g. E1, W3, N5)

  The script queries multiple yearly layers and the daily layer to cover
  the full 24-month window needed for trend calculation.

Output:
  data/raw/henderson_crime_trends.json

Usage:
  python backend/ingest/henderson_crime_trends.py
  python backend/ingest/henderson_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

MAPSERVER_BASE = (
    "https://maps.cityofhenderson.com/arcgis/rest/services"
    "/public/OpenDataPublicSafety/MapServer"
)

# Layer IDs: yearly crime layers from 2014 (layer 6) to 2025 (layer 17),
# plus daily crime data (layer 5) for the most recent ~90 days.
DAILY_LAYER_ID = 5
YEARLY_LAYER_IDS = {
    2014: 6, 2015: 7, 2016: 8, 2017: 9, 2018: 10, 2019: 11,
    2020: 12, 2021: 13, 2022: 14, 2023: 15, 2024: 16, 2025: 17,
}

DEFAULT_OUTPUT_PATH = Path("data/raw/henderson_crime_trends.json")

DATE_FIELD = "OCCURRED_S"
GROUP_FIELD = "BEAT"

HENDERSON_LAT = 36.0397
HENDERSON_LON = -114.9817

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def _query_layer(
    layer_id: int,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Query a single MapServer layer for crime counts grouped by beat."""
    url = f"{MAPSERVER_BASE}/{layer_id}/query"

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
        raise RuntimeError(f"ArcGIS query error (layer {layer_id}): {payload['error']}")

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        beat = str(attrs.get(GROUP_FIELD) or "").strip()
        if not beat:
            continue
        count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
        results[beat] = results.get(beat, 0) + count
    return results


def _layers_for_window(
    start_date: datetime,
    end_date: datetime,
) -> list[int]:
    """Determine which MapServer layers to query for a given date window.

    Returns layer IDs covering the requested window. Uses yearly layers
    where available, and falls back to the daily layer for dates beyond
    the latest yearly layer.
    """
    layers = []
    max_yearly = max(YEARLY_LAYER_IDS.keys())

    # Add yearly layers that overlap with the window
    for year, layer_id in sorted(YEARLY_LAYER_IDS.items()):
        year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        year_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        # Check if this year overlaps with our window
        if year_start < end_date and year_end > start_date:
            layers.append(layer_id)

    # If the window extends beyond the latest yearly data, add the daily layer
    latest_year_end = datetime(max_yearly + 1, 1, 1, tzinfo=timezone.utc)
    if end_date > latest_year_end:
        layers.append(DAILY_LAYER_ID)

    return layers


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """Fetch crime counts by beat for a date window, across multiple layers."""
    layers = _layers_for_window(start_date, end_date)
    print(f"  Querying layers: {layers}")

    combined: dict[str, int] = {}
    for layer_id in layers:
        layer_counts = _query_layer(layer_id, start_date, end_date)
        for beat, count in layer_counts.items():
            combined[beat] = combined.get(beat, 0) + count
    return combined


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
            "region_id": f"henderson_beat_{slug}",
            "district_id": beat,
            "district_name": f"Henderson Beat {beat}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": HENDERSON_LAT,
            "longitude": HENDERSON_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "henderson_crime_trends",
        "source_url": MAPSERVER_BASE,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Henderson HPD crime trends by beat from ArcGIS MapServer."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Henderson crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} beats, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Henderson crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
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
