"""
backend/ingest/dc_crime_trends.py
task: data-049
lane: data

Ingests Washington DC Metropolitan Police crime data and calculates 12-month
crime trends by district.

Source:
  DC GIS MapServer — MPD Crime Feeds
  https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/MPD/MapServer

  Yearly layers: Layer 6=2024, Layer 7=2025, Layer 41=2026, Layer 39=Last30Days
  Key fields: REPORT_DAT, DISTRICT, PSA, OFFENSE, LATITUDE, LONGITUDE

Output:
  data/raw/dc_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/dc_crime_trends.py
  python backend/ingest/dc_crime_trends.py --dry-run
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

MAPSERVER_BASE = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/MPD/MapServer"
)

# Yearly crime layers — map year to layer ID.
# Layer IDs: 0=2008, 1=2009, ..., 6=2024, 7=2025, 41=2026
YEAR_TO_LAYER = {
    2024: 6, 2025: 7, 2026: 41,
}

DEFAULT_OUTPUT_PATH = Path("data/raw/dc_crime_trends.json")

DATE_FIELD = "REPORT_DAT"
GROUP_FIELD = "DISTRICT"

STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# ArcGIS REST queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    """Format datetime as ArcGIS SQL date literal."""
    return f"date '{dt.strftime('%Y-%m-%d')}'"


def _layers_for_range(start_date: datetime, end_date: datetime) -> list[int]:
    """Get layer IDs covering a date range."""
    years = set()
    d = start_date
    while d <= end_date:
        years.add(d.year)
        d += timedelta(days=365)
    years.add(end_date.year)
    return [YEAR_TO_LAYER[y] for y in sorted(years) if y in YEAR_TO_LAYER]


def _fetch_layer_counts(
    layer_id: int,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    url = f"{MAPSERVER_BASE}/{layer_id}/query"

    where_clause = (
        f"{DATE_FIELD} >= {_date_str(start_date)} "
        f"AND {DATE_FIELD} < {_date_str(end_date)}"
    )

    out_statistics = json.dumps([
        {"statisticType": "count", "onStatisticField": "OBJECTID",
         "outStatisticFieldName": "crime_count"},
    ])

    data = {
        "where": where_clause,
        "groupByFieldsForStatistics": GROUP_FIELD,
        "outStatistics": out_statistics,
        "f": "json",
    }

    resp = requests.post(url, data=data, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "error" in payload:
        raise RuntimeError(
            f"ArcGIS query error (layer {layer_id}): {payload['error']}"
        )

    results: dict[str, int] = {}
    for feature in payload.get("features", []):
        attrs = feature["attributes"]
        district = str(attrs.get(GROUP_FIELD) or "").strip()
        if not district:
            continue
        # MapServer uppercases the outStatisticFieldName
        count = int(attrs.get("crime_count") or attrs.get("CRIME_COUNT") or 0)
        results[district] = results.get(district, 0) + count
    return results


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    layers = _layers_for_range(start_date, end_date)
    if not layers:
        print(f"  WARN: no layers available for {start_date.year}–{end_date.year}")
        return {}

    combined: dict[str, int] = {}
    for layer_id in layers:
        print(f"    Querying layer {layer_id}...", end=" ", flush=True)
        layer_counts = _fetch_layer_counts(layer_id, start_date, end_date)
        print(f"{sum(layer_counts.values()):,} crimes")
        for district, count in layer_counts.items():
            combined[district] = combined.get(district, 0) + count
    return combined


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

DC_LAT = 38.9072
DC_LON = -77.0369


def build_trend_records(
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        records.append({
            "region_type": "district",
            "region_id": f"dc_district_{district}",
            "district_id": district,
            "district_name": f"DC District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": DC_LAT,
            "longitude": DC_LON,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "dc_crime_trends",
        "source_url": MAPSERVER_BASE,
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
        description="Ingest DC MPD crime trends by district from ArcGIS MapServer."
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

    print(f"Fetching current 12-month DC crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} districts with current crime data.")

    print(f"\nFetching prior 12-month DC crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} districts with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
