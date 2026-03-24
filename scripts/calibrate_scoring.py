"""
scripts/calibrate_scoring.py
task: data-042
lane: data

Scoring weight calibration — no database required.

Creates synthetic NearbyProject scenarios that represent each QA address
from docs/live_score_validation.md and docs/03_scoring_model.md, runs them
through the live scoring engine, and reports whether the output score falls
in the expected band.

The scenarios are designed to be realistic proxies for what the DB would
return for each address given typical Chicago permit and closure activity.

Usage:
  python scripts/calibrate_scoring.py

Exit codes:
  0 — all scenarios produce scores in the expected band
  1 — one or more scenarios are out of band (calibration issue)

Output format:
  One line per scenario, plus a summary table.
  Compatible with the docs/live_score_validation.md review table.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.models.project import (
    IMPACT_CONSTRUCTION,
    IMPACT_DEMOLITION,
    IMPACT_FULL_CLOSURE,
    IMPACT_LIGHT_PERMIT,
    IMPACT_MULTI_LANE,
    IMPACT_ROAD_CONSTRUCTION,
    IMPACT_SINGLE_LANE,
    Project,
)
from backend.scoring.query import NearbyProject, compute_score

TODAY = date.today()
ACTIVE_SOON  = TODAY + timedelta(days=3)
ACTIVE_LONG  = TODAY + timedelta(days=45)
STARTED_AGO  = TODAY - timedelta(days=14)
STALE_DATE   = TODAY - timedelta(days=120)


def _project(
    source_id: str,
    impact_type: str,
    title: str,
    start: date | None,
    end: date | None,
    status: str = "active",
    severity_hint: str = "MEDIUM",
) -> Project:
    return Project(
        project_id=f"calibration:{source_id}",
        source="calibration",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=None,
        start_date=start,
        end_date=end,
        status=status,
        address=None,
        latitude=None,
        longitude=None,
        severity_hint=severity_hint,
    )


# ---------------------------------------------------------------------------
# Scenario definitions
# Each scenario: (address, expected_band_label, expected_lo, expected_hi, nearby)
# ---------------------------------------------------------------------------

SCENARIOS = [
    # ── 1. High disruption — 1600 W Chicago Ave (West Town) ──────────────────
    # Multi-lane arterial closure (medium distance) + active construction close by.
    # Expected: High (50–74)
    (
        "1600 W Chicago Ave, Chicago, IL",
        "High",
        50, 74,
        "Traffic (multi-lane closure)",
        [
            NearbyProject(
                project=_project(
                    "T1-A", IMPACT_MULTI_LANE,
                    "W Chicago Ave — 2-lane eastbound closure",
                    STARTED_AGO, ACTIVE_SOON,
                    severity_hint="HIGH",
                ),
                distance_m=110.0,
            ),
            NearbyProject(
                project=_project(
                    "T1-B", IMPACT_CONSTRUCTION,
                    "New multi-story residential at 1580 W Chicago Ave",
                    STARTED_AGO, ACTIVE_LONG,
                ),
                distance_m=65.0,
            ),
            NearbyProject(
                project=_project(
                    "T1-C", IMPACT_LIGHT_PERMIT,
                    "Sign permit — 1620 W Chicago Ave",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="LOW",
                ),
                distance_m=40.0,
            ),
        ],
    ),

    # ── 2. High disruption — 700 W Grand Ave (River West) ────────────────────
    # Single-lane closure right outside + road construction one block away.
    # Expected: High (50–74)
    (
        "700 W Grand Ave, Chicago, IL",
        "High",
        50, 74,
        "Traffic (lane closure)",
        [
            NearbyProject(
                project=_project(
                    "T2-A", IMPACT_SINGLE_LANE,
                    "W Grand Ave curb-lane closure — utility work",
                    STARTED_AGO, ACTIVE_SOON,
                    severity_hint="MEDIUM",
                ),
                distance_m=55.0,
            ),
            NearbyProject(
                project=_project(
                    "T2-B", IMPACT_ROAD_CONSTRUCTION,
                    "N Halsted St water main replacement",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="MEDIUM",
                ),
                distance_m=210.0,
            ),
            NearbyProject(
                project=_project(
                    "T2-C", IMPACT_CONSTRUCTION,
                    "Building permit — 680 W Grand Ave",
                    STARTED_AGO, ACTIVE_LONG,
                ),
                distance_m=95.0,
            ),
        ],
    ),

    # ── 3. Moderate disruption — 111 N Halsted St (West Loop) ────────────────
    # Active construction nearby; no active closures — one moderate signal.
    # Expected: Moderate (25–49)
    (
        "111 N Halsted St, Chicago, IL",
        "Moderate",
        25, 49,
        "Noise (construction)",
        [
            NearbyProject(
                project=_project(
                    "T3-A", IMPACT_CONSTRUCTION,
                    "Mixed-use building permit — 90 N Halsted St",
                    STARTED_AGO, ACTIVE_LONG,
                ),
                distance_m=135.0,
            ),
            NearbyProject(
                project=_project(
                    "T3-B", IMPACT_ROAD_CONSTRUCTION,
                    "Sidewalk replacement — W Randolph St",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="MEDIUM",
                ),
                distance_m=185.0,
            ),
            NearbyProject(
                project=_project(
                    "T3-C", IMPACT_LIGHT_PERMIT,
                    "Scaffolding permit — 130 N Halsted St",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="LOW",
                ),
                distance_m=55.0,
            ),
        ],
    ),

    # ── 4. Low disruption — 5800 N Northwest Hwy (Jefferson Park) ───────────
    # Only distant, stale light permit activity.
    # Expected: Low (0–24)
    (
        "5800 N Northwest Hwy, Chicago, IL",
        "Low",
        0, 24,
        "None / background",
        [
            NearbyProject(
                project=_project(
                    "T4-A", IMPACT_LIGHT_PERMIT,
                    "Electrical panel permit — 5820 N Northwest Hwy",
                    STALE_DATE, STALE_DATE + timedelta(days=30),
                    severity_hint="LOW",
                ),
                distance_m=390.0,
            ),
            NearbyProject(
                project=_project(
                    "T4-B", IMPACT_LIGHT_PERMIT,
                    "Roof permit — 5780 N Northwest Hwy",
                    STALE_DATE, STALE_DATE + timedelta(days=20),
                    severity_hint="LOW",
                ),
                distance_m=440.0,
            ),
        ],
    ),

    # ── 5. Low disruption — 11900 S Morgan St (West Pullman) ─────────────────
    # No nearby projects at all.
    # Expected: Low (0–24) — specifically score = 0
    (
        "11900 S Morgan St, Chicago, IL",
        "Low",
        0, 24,
        "None",
        [],
    ),

    # ── 6. Edge case: Severe — full closure at front door ────────────────────
    # Full street closure within 75 m, time-multiplier = 1.0 → 45 pts.
    # 40+ points from one project → Severe per docs/03_scoring_model.md.
    # Expected: Severe (75–100) — actually max single project is 45 → this just
    # reaches the low end of Severe if another signal stacks.
    # Let's use full closure (45) + multi-lane (38×0.8=30.4) = 75 → Severe.
    (
        "233 S Wacker Dr, Chicago, IL",
        "Severe",
        75, 100,
        "Traffic (full closure)",
        [
            NearbyProject(
                project=_project(
                    "T6-A", IMPACT_FULL_CLOSURE,
                    "S Wacker Dr full closure — bridge deck repair",
                    STARTED_AGO, ACTIVE_SOON,
                    severity_hint="HIGH",
                ),
                distance_m=45.0,
            ),
            NearbyProject(
                project=_project(
                    "T6-B", IMPACT_MULTI_LANE,
                    "W Adams St multi-lane restriction",
                    STARTED_AGO, ACTIVE_SOON,
                    severity_hint="HIGH",
                ),
                distance_m=120.0,
            ),
            NearbyProject(
                project=_project(
                    "T6-C", IMPACT_CONSTRUCTION,
                    "High-rise construction — 225 S Wacker",
                    STARTED_AGO, ACTIVE_LONG,
                ),
                distance_m=80.0,
            ),
        ],
    ),

    # ── 7. Edge case: road_construction severity visibility ───────────────────
    # Only road_construction projects — verify they produce > 0 score AND that
    # severity fields are not all LOW (which would indicate the blind spot).
    # Expected: disruption_score > 0, and at least one severity != LOW once fixed.
    (
        "CALIBRATION: road_construction severity check",
        "road_construction_visible",
        None, None,  # no band check; special handling below
        "Traffic (road construction)",
        [
            NearbyProject(
                project=_project(
                    "T7-A", IMPACT_ROAD_CONSTRUCTION,
                    "N Milwaukee Ave full road reconstruction",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="MEDIUM",
                ),
                distance_m=60.0,
            ),
            NearbyProject(
                project=_project(
                    "T7-B", IMPACT_ROAD_CONSTRUCTION,
                    "W Fullerton Ave resurfacing",
                    STARTED_AGO, ACTIVE_LONG,
                    severity_hint="MEDIUM",
                ),
                distance_m=130.0,
            ),
        ],
    ),
]

BAND_LABEL = {
    (0, 24):   "Low",
    (25, 49):  "Moderate",
    (50, 74):  "High",
    (75, 100): "Severe",
}


def band_for_score(score: int) -> str:
    if score <= 24:
        return "Low"
    if score <= 49:
        return "Moderate"
    if score <= 74:
        return "High"
    return "Severe"


def run() -> int:
    failures = 0
    rows = []

    print("══ SCORING CALIBRATION ═══════════════════════════════════════════")

    for address, expected_band, lo, hi, expected_driver, nearby in SCENARIOS:
        result = compute_score(nearby, address)
        score  = result.disruption_score
        actual_band = band_for_score(score)

        # ── Special check for road_construction scenario ──────────────────────
        if expected_band == "road_construction_visible":
            sev_values = list(result.severity.values())
            score_ok   = score > 0
            # After the fix, at least one severity should be non-LOW for two
            # close, active road_construction projects.
            sev_ok     = any(s != "LOW" for s in sev_values)
            status     = "PASS" if (score_ok and sev_ok) else "FAIL"
            if status == "FAIL":
                failures += 1
                if not score_ok:
                    print(f"  FAIL [{address}] score={score} (expected >0)")
                if not sev_ok:
                    print(
                        f"  FAIL [{address}] all severity=LOW despite active road_construction — "
                        f"blind spot not fixed (severity={result.severity})"
                    )
            else:
                print(
                    f"  PASS [{address}] score={score}, "
                    f"severity={result.severity} (road_construction visible)"
                )
            rows.append({
                "address": address,
                "expected": "score>0 + any sev!=LOW",
                "actual_score": score,
                "actual_severity": result.severity,
                "confidence": result.confidence,
                "dominant_driver": expected_driver,
                "pass_fail": status,
                "notes": "; ".join(result.top_risks[:1]),
            })
            continue

        # ── Standard band check ───────────────────────────────────────────────
        in_band = lo <= score <= hi
        status  = "PASS" if in_band else "FAIL"
        if not in_band:
            failures += 1
            print(
                f"  FAIL [{address}] score={score} "
                f"(expected {expected_band} {lo}–{hi}, got {actual_band})"
            )
        else:
            print(
                f"  PASS [{address}] score={score} "
                f"({actual_band} ✓ in {lo}–{hi})"
            )

        rows.append({
            "address": address,
            "expected_band": f"{expected_band} ({lo}–{hi})",
            "actual_score": score,
            "actual_band": actual_band,
            "confidence": result.confidence,
            "dominant_driver": expected_driver,
            "pass_fail": status,
            "notes": "; ".join(result.top_risks[:1]),
        })

    print()
    print("══ SUMMARY TABLE ══════════════════════════════════════════════════")
    print(f"{'Address':<48} {'Exp':>18} {'Score':>6} {'Band':>10} {'Conf':>7} {'P/F':>5}")
    print("─" * 100)
    for row in rows:
        addr = row["address"][:47]
        exp  = row.get("expected_band", row.get("expected", ""))[:18]
        score = str(row["actual_score"])
        band = row.get("actual_band", "—")
        conf = row["confidence"]
        pf   = row["pass_fail"]
        print(f"{addr:<48} {exp:>18} {score:>6} {band:>10} {conf:>7} {pf:>5}")

    print()
    if failures == 0:
        print(f"All {len(SCENARIOS)} scenarios passed.")
    else:
        print(f"{failures}/{len(SCENARIOS)} scenario(s) FAILED — calibration adjustment needed.")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
