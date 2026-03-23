"""
backend/ingest/columbus_crime_trends.py
task: data-050
lane: data

Ingests Columbus Division of Police (CPD) crime data and calculates
12-month crime trends by police zone.

STATUS: DATA UNAVAILABLE
  Columbus suffered a ransomware attack in July 2024 that took their public
  crime data portal offline. As of March 2026, no public crime incident API
  has been restored. The only available mapping is the LexisNexis Community
  Crime Map (communitycrimemap.com), which has no public bulk-data API.

  This script will exit gracefully until an API becomes available.

  Previous (non-functional) source:
    ArcGIS FeatureServer -- opendata.columbus.gov (offline)

Output:
  data/raw/columbus_crime_trends.json -- zone crime trend records

Usage:
  python backend/ingest/columbus_crime_trends.py
  python backend/ingest/columbus_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_PATH = Path("data/raw/columbus_crime_trends.json")

COLUMBUS_LAT = 39.9612
COLUMBUS_LON = -82.9988

STABLE_THRESHOLD_PCT = 5.0

# Columbus crime data has been offline since the July 2024 ransomware attack.
# When a new API becomes available, update this URL and the fetch function.
DATA_UNAVAILABLE_REASON = (
    "Columbus crime data has been offline since the July 2024 ransomware attack. "
    "No public crime incident API is currently available. "
    "See: https://www.nbc4i.com/news/local-news/columbus/ for updates."
)


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
        "source_url": "unavailable",
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Columbus CPD crime trends by zone."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"SKIPPED: {DATA_UNAVAILABLE_REASON}")
    print("Columbus crime trends will produce 0 records until data is restored.")

    records: list[dict] = []

    if args.dry_run:
        print("\nDry-run mode: no data to fetch or write.")
        return

    write_staging_file(records, args.output)
    print("Done (0 records).")


if __name__ == "__main__":
    main()
