"""
backend/app/services/livability.py

Livability score computation — extracted from main.py.

Contains:
  - _LIVABILITY_WEIGHTS — component weight config from env vars
  - _school_rating_to_score() — converts school rating text to 0-100
  - _compute_livability_score() — full composite scoring with HPI bonus
  - _extract_zip() — extracts 5-digit ZIP from address string
"""

from __future__ import annotations

import os
import re


# ---------------------------------------------------------------------------
# Weights (configurable via env vars, defaults match methodology page)
# ---------------------------------------------------------------------------

_LIVABILITY_WEIGHTS = {
    "disruption_risk": float(os.environ.get("LIVABILITY_W_DISRUPTION", "0.35")),
    "crime_trend": float(os.environ.get("LIVABILITY_W_CRIME", "0.25")),
    "school_rating": float(os.environ.get("LIVABILITY_W_SCHOOL", "0.20")),
    "demographics_stability": float(os.environ.get("LIVABILITY_W_DEMOGRAPHICS", "0.10")),
    "flood_environmental": float(os.environ.get("LIVABILITY_W_FLOOD", "0.10")),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _school_rating_to_score(v) -> float:
    if v is None:
        return 50.0
    text = str(v).strip().upper()
    if text in {"EXCELLENT", "LEVEL 1+"}:
        return 92.0
    if text in {"STRONG", "LEVEL 1"}:
        return 78.0
    if text in {"AVERAGE", "LEVEL 2"}:
        return 58.0
    if text in {"WEAK", "LEVEL 3"}:
        return 34.0
    if text in {"VERY WEAK", "LEVEL 4"}:
        return 20.0
    try:
        n = float(text)
        if n <= 5:
            return max(0.0, min(100.0, n * 20.0))
        return max(0.0, min(100.0, n))
    except Exception:
        return 50.0


def _extract_zip(raw: str) -> str | None:
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", raw)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Composite livability score
# ---------------------------------------------------------------------------

def _compute_livability_score(
    *,
    disruption_score: int,
    neighborhood_context: dict | None,
    lat: float,
    lon: float,
    conn,
    zip_code: str | None = None,
) -> tuple[int, dict]:
    neighborhood_context = neighborhood_context or {}
    weights = _LIVABILITY_WEIGHTS

    # 1) disruption risk (inverted)
    disruption_component = max(0.0, min(100.0, 100.0 - float(disruption_score)))

    # 2) crime trend
    trend = str(neighborhood_context.get("crime_trend") or "").upper()
    crime_component = {"DECREASING": 85.0, "STABLE": 60.0, "INCREASING": 25.0}.get(trend, 50.0)
    trend_pct = neighborhood_context.get("crime_trend_pct")
    if trend_pct is not None:
        crime_component = max(0.0, min(100.0, crime_component + float(trend_pct) * -0.4))

    # 3) school rating (nearest school from neighborhood_quality)
    school_component = 50.0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT school_rating
                FROM neighborhood_quality
                WHERE region_type = 'school' AND geom IS NOT NULL
                ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                LIMIT 1
                """,
                (lon, lat),
            )
            row = cur.fetchone()
            if row:
                school_component = _school_rating_to_score(row[0])
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    # 4) demographics/stability (income percentile + low vacancy)
    demo_component = 50.0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT income_percentile, vacancy_rate
                FROM (
                    SELECT
                        region_id,
                        median_income,
                        vacancy_rate,
                        cume_dist() OVER (ORDER BY median_income) AS income_percentile,
                        geom
                    FROM neighborhood_quality
                    WHERE region_type = 'census_tract'
                      AND geom IS NOT NULL
                      AND median_income IS NOT NULL
                ) q
                ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                LIMIT 1
                """,
                (lon, lat),
            )
            row = cur.fetchone()
            if row:
                income_pct = float(row[0]) if row[0] is not None else 0.5
                vacancy = float(row[1]) if row[1] is not None else 8.0
                vacancy_score = max(0.0, min(100.0, 100.0 - (vacancy * 8.0)))
                demo_component = max(0.0, min(100.0, (income_pct * 100.0 * 0.65) + (vacancy_score * 0.35)))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    # 5) flood/environment
    flood_risk = str(neighborhood_context.get("flood_risk") or "").upper()
    flood_component = {"MINIMAL": 90.0, "MODERATE": 65.0, "HIGH": 25.0}.get(flood_risk, 50.0)

    # 6) HPI price trend bonus/penalty (up to ±5 points)
    hpi_bonus = 0.0
    hpi_data: dict | None = None
    if zip_code and conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT hpi_index_value, hpi_1yr_change, hpi_5yr_change,
                           hpi_10yr_change, hpi_period
                    FROM neighborhood_quality
                    WHERE region_type = 'zip' AND region_id = %s
                    LIMIT 1
                    """,
                    (zip_code,),
                )
                row = cur.fetchone()
                if row and row[1] is not None:
                    hpi_data = {
                        "hpi_index_value": float(row[0]) if row[0] else None,
                        "hpi_1yr_change": float(row[1]) if row[1] else None,
                        "hpi_5yr_change": float(row[2]) if row[2] else None,
                        "hpi_10yr_change": float(row[3]) if row[3] else None,
                        "hpi_period": row[4],
                    }
                    yr1 = float(row[1])
                    hpi_bonus = max(-5.0, min(5.0, yr1 * 0.3))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    components = {
        "disruption_risk": disruption_component,
        "crime_trend": crime_component,
        "school_rating": school_component,
        "demographics_stability": demo_component,
        "flood_environmental": flood_component,
    }
    weighted = {
        k: round(v * weights[k], 1)
        for k, v in components.items()
    }
    livability_score = int(round(sum(weighted.values()) + hpi_bonus))
    livability_score = max(0, min(100, livability_score))

    breakdown: dict = {
        "weights": weights,
        "components": {
            k: {"raw_score": round(components[k], 1), "weighted_contribution": weighted[k]}
            for k in components
        },
    }
    if hpi_bonus != 0.0:
        breakdown["hpi_bonus"] = round(hpi_bonus, 1)
    if hpi_data:
        breakdown["hpi"] = hpi_data

    return livability_score, breakdown
