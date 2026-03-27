"""
backend/ingest/albuquerque_crime_trends.py
task: data-050
lane: data

Ingests Albuquerque Police Department (APD) crime data and calculates
12-month crime trends by area command (district).

Source:
  ArcGIS Hub — cabq.gov/abqdata (Albuquerque Open Data Portal)
  Service: APD Crime Statistics

  not live-verified service URL before production:
    python backend/ingest/albuquerque_crime_trends.py --discover
    Or visit: https://cabq.gov/abqdata and search "crime" or "APD"
    Or search: https://abq.maps.arcgis.com

  Verified service URL:
    https://services.arcgis.com/CWv1abTnC3urn4bV/arcgis/rest/services
    /Incidents/FeatureServer/0

  WARNING: Dataset frozen at November 17, 2024 (108,395 records).
  No newer crime data found on this ArcGIS org. Returns 0 records for
  any date window after 2024-11-17. Needs a new data source.

  Key fields (verified via sample query):
    ReportDateTime — date of incident report
    CMLegend       — crime category (ASSAULT, BURGLARY, ROBBERY, etc.)
    BlockAddress   — 100-block level address (no lat/lon or area command)

Output:
  data/raw/albuquerque_crime_trends.json — area command crime trend records

Usage:
  python backend/ingest/albuquerque_crime_trends.py
  python backend/ingest/albuquerque_crime_trends.py --dry-run
  python backend/ingest/albuquerque_crime_trends.py --discover
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

# Verified: ABQ Incidents on ArcGIS Online
# Note: only ~6 months of rolling data available; no AREA_COMMAND field,
# grouping by CMLegend (crime category) instead.
FEATURESERVER_URL = (
    "https://services.arcgis.com/CWv1abTnC3urn4bV/arcgis/rest/services"
    "/Incidents/FeatureServer/0"
)
PORTAL_ORG_ID = "CWv1abTnC3urn4bV"

DEFAULT_OUTPUT_PATH = Path("data/raw/albuquerque_crime_trends.json")

# Verified field names — no AREA_COMMAND in data, using CMLegend (crime category)
DATE_FIELD = "ReportDateTime"
GROUP_FIELD = "CMLegend"

ALBUQUERQUE_LAT = 35.0844
ALBUQUERQUE_LON = -106.6504

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


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
        category = str(attrs.get(GROUP_FIELD) or "").strip()
        if not category:
            continue
        count = int(attrs.get("crime_count", 0) or attrs.get("CRIME_COUNT", 0))
        results[category] = results.get(category, 0) + count
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
    all_categories = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for category in sorted(all_categories):
        current_count = current_data.get(category, 0)
        prior_count = prior_data.get(category, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = category.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "crime_category",
            "region_id": f"albuquerque_crime_{slug}",
            "district_id": category,
            "district_name": f"Albuquerque — {category.title()}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": ALBUQUERQUE_LAT,
            "longitude": ALBUQUERQUE_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "albuquerque_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def discover(org_id: str) -> None:
    """Query ArcGIS Hub for crime datasets."""
    hub_url = "https://hub.arcgis.com/api/v3/search"
    params = {
        "q": "APD crime incidents albuquerque",
        "filter[orgid]": org_id,
        "fields[datasets]": "id,name,url",
        "page[size]": 5,
    }
    try:
        resp = requests.get(hub_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print("ArcGIS Hub search results (APD crime/incidents):")
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            print(f"  {attrs.get('name','?')} — {attrs.get('url','?')}")
    except Exception as exc:
        print(f"Discover failed: {exc}")
    print(f"\nAlso try: https://cabq.gov/abqdata (search 'crime' or 'APD')")
    print(f"Or: https://abq.maps.arcgis.com (search 'crime')")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Albuquerque APD crime trends by area command from ArcGIS."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Query ArcGIS Hub for available crime datasets.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.discover:
        discover(PORTAL_ORG_ID)
        return

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Albuquerque crime counts "
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} categories, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Albuquerque crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} categories, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} area command trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} categories")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
