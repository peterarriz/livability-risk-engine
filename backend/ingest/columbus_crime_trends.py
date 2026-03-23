"""
backend/ingest/columbus_crime_trends.py
task: data-050
lane: data

Ingests Columbus Division of Police (CPD) crime data and calculates
12-month crime trends by police zone.

Source:
  ArcGIS FeatureServer — opendata.columbus.gov
  Service: CPD Offense Data (ArcGIS Hub, org ID 9yy6msODkIBzkUXU)

  MUST VERIFY service URL before production:
    python backend/ingest/columbus_crime_trends.py --discover
    Or visit: https://opendata.columbus.gov and search "crime" or "offense"

  Estimated URL:
    https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services
    /CPD_Offense_Data/FeatureServer/0

  Verify sample record:
    curl "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/CPD_Offense_Data/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json"

  Key fields (verify via --discover or sample query):
    REPORT_DATE  — date of incident
    ZONE         — Columbus police zone
    Latitude, Longitude — coordinates

Output:
  data/raw/columbus_crime_trends.json — zone crime trend records

Usage:
  python backend/ingest/columbus_crime_trends.py
  python backend/ingest/columbus_crime_trends.py --dry-run
  python backend/ingest/columbus_crime_trends.py --discover
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

# MUST VERIFY: visit https://opendata.columbus.gov, search "crime" or "offense",
# open the dataset, click "API" → copy FeatureServer URL.
FEATURESERVER_URL = (
    "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services"
    "/CPD_Offense_Data/FeatureServer/0"
)
PORTAL_ORG_ID = "9yy6msODkIBzkUXU"

DEFAULT_OUTPUT_PATH = Path("data/raw/columbus_crime_trends.json")

# MUST VERIFY field names via sample query:
#   curl "{FEATURESERVER_URL}/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json"
DATE_FIELD = "REPORT_DATE"
GROUP_FIELD = "ZONE"

COLUMBUS_LAT = 39.9612
COLUMBUS_LON = -82.9988

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
        zone = str(attrs.get(GROUP_FIELD) or "").strip()
        if not zone:
            continue
        results[zone] = results.get(zone, 0) + int(attrs.get("crime_count", 0))
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
    all_zones = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zone in sorted(all_zones):
        current_count = current_data.get(zone, 0)
        prior_count = prior_data.get(zone, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = zone.lower().replace(" ", "_")
        records.append({
            "region_type": "zone",
            "region_id": f"columbus_zone_{slug}",
            "district_id": zone,
            "district_name": f"Columbus Police Zone {zone}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": COLUMBUS_LAT,
            "longitude": COLUMBUS_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "columbus_crime_trends",
        "source_url": FEATURESERVER_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def discover(org_id: str) -> None:
    """Query ArcGIS Hub for crime/offense datasets in this org."""
    hub_url = f"https://hub.arcgis.com/api/v3/search"
    params = {
        "q": "crime offense incidents",
        "filter[orgid]": org_id,
        "fields[datasets]": "id,name,url",
        "page[size]": 5,
    }
    try:
        resp = requests.get(hub_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print("ArcGIS Hub search results (crime/offense):")
        for item in data.get("data", []):
            attrs = item.get("attributes", {})
            print(f"  {attrs.get('name','?')} — {attrs.get('url','?')}")
    except Exception as exc:
        print(f"Discover failed: {exc}")
    print(f"\nAlso try: https://opendata.columbus.gov (search 'crime' or 'offense')")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Columbus CPD crime trends by zone from ArcGIS FeatureServer."
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

    print(f"Fetching current 12-month Columbus crime counts "
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} zones, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Columbus crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} zones, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} zone trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} zones")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
