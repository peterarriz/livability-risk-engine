"""
backend/ingest/portland_crime_trends.py
task: data-047
lane: data

Ingests Portland Police Bureau crime data and calculates 12-month crime trends
by offense category.

Source:
  Portland Maps Open Data — Public Crime MapServer
  https://www.portlandmaps.com/arcgis/rest/services/Public/Crime/MapServer

  Verified 2026-03-23 via direct query.

  Three "All Locations" layers cover all crime types:
    Layer 1  — All Property Crime Locations
    Layer 40 — All Person Crime Locations
    Layer 59 — All Society Crime Locations

  Key fields (shared across all three layers):
    OBJECTID              — row ID
    REPORTED_DATETIME     — epoch milliseconds
    CrimeType             — specific offense (e.g. "Theft From Motor Vehicle")
    OffenseGroupDescription — offense group (e.g. "Larceny Offenses")
    CategoryName          — top-level category (Property / Person / Society)

  Note: These layers have NO precinct, neighborhood, or ZIP field. Coordinates
  are embedded in point geometry (Web Mercator). We group by
  OffenseGroupDescription across all three layers.

  The MapServer requires POST for outStatistics queries and uses
  date '...' SQL literals (not TIMESTAMP '...').

Method:
  1. Query crime counts by OffenseGroupDescription for the last 12 months
     across all three layers.
  2. Query crime counts by OffenseGroupDescription for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.

Output:
  data/raw/portland_crime_trends.json — offense-group crime trend records

Usage:
  python backend/ingest/portland_crime_trends.py
  python backend/ingest/portland_crime_trends.py --dry-run
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
    "https://www.portlandmaps.com/arcgis/rest/services/Public/Crime/MapServer"
)

# All-locations layers covering Property, Person, and Society crimes.
CRIME_LAYER_IDS = [1, 40, 59]

DEFAULT_OUTPUT_PATH = Path("data/raw/portland_crime_trends.json")

DATE_FIELD = "REPORTED_DATETIME"          # epoch milliseconds
GROUP_FIELD = "OffenseGroupDescription"   # offense group

# Portland city center (used as fallback — no per-group coordinates available).
PORTLAND_LAT = 45.5152
PORTLAND_LON = -122.6784

# Changes within ±5% are classified as STABLE.
STABLE_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# ArcGIS REST queries
# ---------------------------------------------------------------------------

def _date_str(dt: datetime) -> str:
    """Format datetime as ArcGIS SQL date literal: date 'YYYY-MM-DD'."""
    return f"date '{dt.strftime('%Y-%m-%d')}'"


def _fetch_layer_counts(
    layer_id: int,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """
    Fetch crime counts grouped by OffenseGroupDescription for one layer
    within a date range.  Returns dict: group_name → count.
    """
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
        group = str(attrs.get(GROUP_FIELD) or "").strip()
        if not group:
            continue
        results[group] = results.get(group, 0) + int(attrs.get("crime_count", 0))
    return results


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> dict[str, int]:
    """
    Fetch total crime counts by offense group across all crime layers.
    Returns dict: group_name → count.
    """
    combined: dict[str, int] = {}
    for layer_id in CRIME_LAYER_IDS:
        layer_counts = _fetch_layer_counts(layer_id, start_date, end_date)
        for group, count in layer_counts.items():
            combined[group] = combined.get(group, 0) + count
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

def build_trend_records(
    current_data: dict[str, int],
    prior_data: dict[str, int],
) -> list[dict]:
    """
    Merge current and prior crime counts to produce trend records.
    All offense groups appearing in either window get a record.
    """
    all_groups = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for group in sorted(all_groups):
        current_count = current_data.get(group, 0)
        prior_count = prior_data.get(group, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        slug = group.lower().replace(" ", "_").replace("/", "_")
        records.append({
            "region_type": "city",
            "region_id": f"portland_offense_{slug}",
            "district_id": group,
            "district_name": f"Portland — {group}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": PORTLAND_LAT,
            "longitude": PORTLAND_LON,
        })
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "portland_crime_trends",
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
        description="Ingest Portland PPB crime trends by offense group from ArcGIS MapServer."
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

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Portland crime counts ({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    print(f"  Querying layers {CRIME_LAYER_IDS} ...")
    try:
        current_data = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} offense groups, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Portland crime counts ({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    print(f"  Querying layers {CRIME_LAYER_IDS} ...")
    try:
        prior_data = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} offense groups, {total_prior:,} total crimes.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} offense-group trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} groups")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
