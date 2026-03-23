"""
backend/scoring/rewrite.py
task: data-042

Rewrites raw permit/closure signal strings into clean 1-line titles and
1-sentence plain-English descriptions using the Claude API.

Results are cached in the signal_rewrites DB table (keyed on project_id)
so the API is called at most once per unique project regardless of how
many /score requests reference it.

Graceful degradation:
  - ANTHROPIC_API_KEY not set    → enrichment skipped, original dicts returned
  - signal_rewrites table absent → cache read/write silently skipped
  - Claude API call fails        → that signal returned with null rewrite fields
  - anthropic package absent     → ImportError caught, enrichment skipped

Usage (from _score_live in main.py):
    from backend.scoring.rewrite import enrich_top_risk_details
    result_dict["top_risk_details"] = enrich_top_risk_details(
        result_dict.get("top_risk_details") or [], conn
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection
# Configurable via env var so operators can trade quality for speed/cost.
# Default: claude-opus-4-6 (recommended for quality signal rewrites).
# Override: CLAUDE_REWRITE_MODEL=claude-haiku-4-5 to reduce latency.
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("CLAUDE_REWRITE_MODEL", "claude-opus-4-6")

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You rewrite raw municipal permit and street-closure metadata into "
    "concise, plain-English signal labels for a real-estate livability app. "
    "Always respond with valid JSON only — no markdown fences, no commentary."
)

_USER_TEMPLATE = """\
Rewrite this disruption signal into a clean title and one-sentence description.

Metadata:
  impact_type : {impact_type}
  raw_title   : {raw_title}
  address     : {address}
  distance_ft : {distance_ft}
  start_date  : {start_date}
  end_date    : {end_date}
  source      : {source}

Rules:
  - title: ≤60 chars, title-case, no permit codes, starts with an action noun
    Good examples: "Lane closure on Huron St, 144 ft away"
                   "Construction permit on N Damen Ave, 280 ft away"
                   "Full street closure on W Grand Ave, 95 ft away"
  - description: ≤120 chars, one complete sentence, plain English.
    Include street name, distance, and end_date if present (e.g. "active through April 15").
    Good example: "Permitted work closing a lane on Huron between #900–909, active through April 15."
  - Never include raw permit codes (GenOpening, GenOccupy, source IDs, etc.)
  - Never include raw meter distances — convert to feet or omit

Return exactly this JSON (no other text):
{{"title": "<title>", "description": "<description>"}}
"""


def _meters_to_feet(meters: Optional[float]) -> Optional[int]:
    if meters is None:
        return None
    return round(meters * 3.28084)


def _extract_json(text: str) -> str:
    """Pull the first {...} block from text (strips markdown fences if present)."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    return match.group(0) if match else text


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------


def _call_claude(project: dict) -> dict:
    """
    Call the Claude API to generate a clean title + description for one signal.

    Returns {"title": str, "description": str}.
    Raises on API or JSON parse failure.
    """
    import anthropic  # lazy import — only needed when key is set

    client = anthropic.Anthropic()

    distance_ft = _meters_to_feet(project.get("distance_m"))
    prompt = _USER_TEMPLATE.format(
        impact_type=project.get("impact_type") or "unknown",
        raw_title=project.get("title") or "(no title)",
        address=project.get("address") or "(unknown address)",
        distance_ft=f"{distance_ft} ft" if distance_ft is not None else "unknown",
        start_date=project.get("start_date") or "unknown",
        end_date=project.get("end_date") or "not specified",
        source=project.get("source") or "unknown",
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = next(
        (b.text for b in response.content if b.type == "text"), "{}"
    ).strip()

    parsed = json.loads(_extract_json(raw_text))
    return {
        "title": str(parsed.get("title", "")).strip(),
        "description": str(parsed.get("description", "")).strip(),
    }


# ---------------------------------------------------------------------------
# DB cache helpers
# ---------------------------------------------------------------------------


def _load_cached(project_id: str, conn) -> Optional[dict]:
    """
    Return cached rewrite for project_id, or None if not found / table absent.
    Rolls back on any DB error so the caller's connection stays usable.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rewritten_title, rewritten_description
                FROM signal_rewrites
                WHERE project_id = %s
                """,
                (project_id,),
            )
            row = cur.fetchone()
            if row:
                return {"title": row[0], "description": row[1]}
    except Exception as exc:
        log.debug("signal_rewrites cache read skipped project_id=%s: %s", project_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass
    return None


def _store_cached(project_id: str, rewrite: dict, conn) -> None:
    """
    Persist a rewrite result.  Non-fatal if the table does not exist yet.
    Rolls back on error so the caller's connection stays usable.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signal_rewrites (project_id, rewritten_title, rewritten_description)
                VALUES (%s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE
                    SET rewritten_title       = EXCLUDED.rewritten_title,
                        rewritten_description = EXCLUDED.rewritten_description,
                        updated_at            = now()
                """,
                (project_id, rewrite["title"], rewrite["description"]),
            )
            conn.commit()
    except Exception as exc:
        log.debug("signal_rewrites cache write skipped project_id=%s: %s", project_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_top_risk_details(details: list[dict], conn) -> list[dict]:
    """
    Add rewritten_title and rewritten_description to each top_risk_detail dict.

    Strategy (cache-first):
      1. Look up project_id in signal_rewrites cache table.
      2. On miss: call Claude API, persist result to cache.
      3. On any failure: add null fields and continue (never raises).

    If ANTHROPIC_API_KEY is not set or the anthropic package is not installed,
    the function returns the original list unchanged (all-null rewrite fields
    are NOT added in this case, to keep the response shape clean).

    Args:
        details: List of top_risk_detail dicts from compute_score().
        conn:    Open psycopg2 connection used for cache reads/writes.

    Returns:
        Same list with rewritten_title and rewritten_description added to each item.
    """
    if not details:
        return details

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.debug("ANTHROPIC_API_KEY not set — skipping signal rewrite enrichment")
        return details

    try:
        import anthropic  # noqa: F401 — verify package available before looping
    except ImportError:
        log.warning("anthropic package not installed — skipping signal rewrite enrichment")
        return details

    enriched = []
    for detail in details:
        project_id = detail.get("project_id", "")
        rewrite: dict = {"title": None, "description": None}

        try:
            cached = _load_cached(project_id, conn) if project_id else None
            if cached:
                rewrite = cached
                log.debug("signal_rewrite cache_hit project_id=%s", project_id)
            else:
                rewrite = _call_claude(detail)
                log.info(
                    "signal_rewrite claude_call project_id=%s title=%r",
                    project_id,
                    rewrite.get("title"),
                )
                if project_id and conn:
                    _store_cached(project_id, rewrite, conn)
        except Exception as exc:
            log.warning(
                "signal_rewrite failed project_id=%s error=%s — using null fields",
                project_id,
                exc,
            )

        enriched.append(
            {
                **detail,
                "rewritten_title": rewrite.get("title") or None,
                "rewritten_description": rewrite.get("description") or None,
            }
        )

    return enriched
