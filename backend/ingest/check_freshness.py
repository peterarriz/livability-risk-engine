"""
backend/ingest/check_freshness.py
task: data-010
lane: data

Lightweight freshness check for the two MVP staging files.

Reads the `ingested_at` timestamp written by the ingest scripts and
reports whether each source is within its expected refresh window.
Exits non-zero if any required source is stale so CI or manual review
can catch a missed refresh quickly.

Usage:
  # Check both staging files (default paths):
  python backend/ingest/check_freshness.py

  # Custom paths:
  python backend/ingest/check_freshness.py \\
      --permits-file data/raw/building_permits.json \\
      --closures-file data/raw/street_closures.json

  # Machine-readable output:
  python backend/ingest/check_freshness.py --json

Freshness thresholds (from docs/05_data_sources_chicago.md):
  Building permits : 26 hours  (daily refresh with 2-hour grace)
  Street closures  : 26 hours  (daily refresh with 2-hour grace)

Exit codes:
  0  All required sources are fresh.
  1  One or more required sources are stale or missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------

# Permits and closures should both refresh daily.
# 26 hours gives a 2-hour grace window over a 24-hour cron cadence.
DEFAULT_MAX_AGE_HOURS = 26

SOURCE_CONFIG = [
    {
        "name": "chicago_building_permits",
        "label": "Building permits",
        "default_path": Path("data/raw/building_permits.json"),
        "max_age_hours": DEFAULT_MAX_AGE_HOURS,
        "required": True,
    },
    {
        "name": "chicago_street_closures",
        "label": "Street closures",
        "default_path": Path("data/raw/street_closures.json"),
        "max_age_hours": DEFAULT_MAX_AGE_HOURS,
        "required": True,
    },
]


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

def check_staging_file(
    path: Path,
    max_age_hours: int,
    now: datetime,
) -> dict:
    """
    Read a staging file and return a freshness result dict with keys:
      path, exists, ingested_at, age_hours, fresh, record_count, error
    """
    result = {
        "path": str(path),
        "exists": False,
        "ingested_at": None,
        "age_hours": None,
        "fresh": False,
        "record_count": None,
        "error": None,
    }

    if not path.exists():
        result["error"] = "File not found"
        return result

    result["exists"] = True

    try:
        with path.open(encoding="utf-8") as f:
            staging = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        result["error"] = f"Could not read file: {exc}"
        return result

    ingested_str = staging.get("ingested_at")
    if not ingested_str:
        result["error"] = "Missing ingested_at field"
        return result

    try:
        ingested_at = datetime.fromisoformat(ingested_str.replace("Z", "+00:00"))
    except ValueError:
        result["error"] = f"Cannot parse ingested_at: {ingested_str!r}"
        return result

    age = now - ingested_at
    age_hours = age.total_seconds() / 3600

    result["ingested_at"] = ingested_str
    result["age_hours"] = round(age_hours, 1)
    result["record_count"] = staging.get("record_count")
    result["fresh"] = age_hours <= max_age_hours

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _status_icon(fresh: bool, required: bool) -> str:
    if fresh:
        return "OK "
    return "STALE" if required else "WARN "


def print_report(checks: list[dict], config: list[dict]) -> None:
    print("\n── Staging file freshness check ────────────────────")
    for check, cfg in zip(checks, config):
        icon = _status_icon(check["fresh"], cfg["required"])
        label = cfg["label"]
        if check["error"]:
            print(f"  [{icon}] {label}: {check['error']} ({check['path']})")
        else:
            age_str = f"{check['age_hours']}h old"
            rec_str = f"{check['record_count']} records" if check["record_count"] is not None else "unknown records"
            threshold = f"threshold: {cfg['max_age_hours']}h"
            print(f"  [{icon}] {label}: {age_str}, {rec_str} ({threshold})")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that MVP staging files are within their freshness threshold."
    )
    parser.add_argument(
        "--permits-file",
        type=Path,
        default=SOURCE_CONFIG[0]["default_path"],
        help=f"Path to building permits staging file (default: {SOURCE_CONFIG[0]['default_path']})",
    )
    parser.add_argument(
        "--closures-file",
        type=Path,
        default=SOURCE_CONFIG[1]["default_path"],
        help=f"Path to street closures staging file (default: {SOURCE_CONFIG[1]['default_path']})",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Override freshness threshold in hours for both sources (default: {DEFAULT_MAX_AGE_HOURS})",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output results as JSON instead of human-readable text.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now = datetime.now(timezone.utc)

    # Apply custom paths and optional threshold override.
    config = [
        {**SOURCE_CONFIG[0], "default_path": args.permits_file, "max_age_hours": args.max_age_hours},
        {**SOURCE_CONFIG[1], "default_path": args.closures_file, "max_age_hours": args.max_age_hours},
    ]

    checks = [
        check_staging_file(cfg["default_path"], cfg["max_age_hours"], now)
        for cfg in config
    ]

    if args.json_output:
        output = [
            {
                "source": cfg["name"],
                "label": cfg["label"],
                "required": cfg["required"],
                **check,
            }
            for cfg, check in zip(config, checks)
        ]
        print(json.dumps(output, indent=2))
    else:
        print_report(checks, config)

    # Exit 1 if any required source is stale or errored.
    any_failed = any(
        not check["fresh"] and cfg["required"]
        for check, cfg in zip(checks, config)
    )
    if any_failed:
        if not args.json_output:
            print(
                "One or more required sources are stale or missing.\n"
                "Run the ingest scripts to refresh them:\n"
                "  python backend/ingest/building_permits.py\n"
                "  python backend/ingest/street_closures.py"
            )
        sys.exit(1)

    if not args.json_output:
        print("All required sources are fresh.")


if __name__ == "__main__":
    main()
