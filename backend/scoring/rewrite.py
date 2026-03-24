"""
backend/scoring/rewrite.py
tasks: data-042, data-043

Enriches each top_risk_detail with a 4-field Claude-generated display card:
  display_title   — short human title (≤60 chars)
  distance        — pre-formatted distance string, e.g. "~1,100 ft away"
  description     — one-sentence factual description (≤120 chars)
  why_it_matters  — one-sentence practical impact explanation (≤120 chars)

Results are cached in the signal_display DB table (keyed on project_id) so the
Claude API is called at most once per unique permit regardless of how many /score
requests reference it.

Graceful degradation (never raises to the caller):
  - ANTHROPIC_API_KEY not set    → Option A formatter runs for every signal
  - signal_display table absent  → cache read/write silently skipped
  - Claude API call fails        → Option A formatter used for that signal
  - anthropic package absent     → Option A formatter runs for every signal

Option A formatter is a deterministic string-template fallback that derives all
four fields from the raw permit metadata without calling the AI API.

Backward compat:
  rewritten_title / rewritten_description (data-042) are still added to each
  dict so older frontend code that reads those keys continues to work.

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
import hashlib
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("CLAUDE_REWRITE_MODEL", "claude-opus-4-6")

# ---------------------------------------------------------------------------
# Option A: deterministic fallback formatter
# Mirrors the heuristic logic in the frontend's buildRiskCards / inferDriverTitle
# / deriveDriverRationale.  Called when the Claude API is unavailable or fails.
# ---------------------------------------------------------------------------

_IMPACT_TYPE_LABELS: dict[str, str] = {
    "closure_full": "Full street closure",
    "closure_multi_lane": "Multi-lane closure",
    "closure_single_lane": "Lane closure",
    "demolition": "Demolition",
    "construction": "Construction permit",
    "light_permit": "Permitted work",
}

_WHY_IT_MATTERS_MAP: dict[str, str] = {
    "closure_full": (
        "A full closure will redirect all traffic and significantly affect "
        "access on nearby blocks."
    ),
    "closure_multi_lane": (
        "This lane closure reduces available travel lanes and may cause "
        "access and parking friction."
    ),
    "closure_single_lane": (
        "A single-lane closure may slow traffic and affect curb access "
        "in the immediate area."
    ),
    "demolition": (
        "Demolition brings heavy equipment, noise, dust, and restricted "
        "pedestrian access to nearby blocks."
    ),
    "construction": (
        "Active permitted construction nearby provides a concrete basis "
        "for elevated short-term disruption."
    ),
    "light_permit": (
        "Minor permitted work is unlikely to cause major disruption "
        "but is worth monitoring."
    ),
}


def _meters_to_feet(meters: Optional[float]) -> Optional[int]:
    if meters is None:
        return None
    return round(meters * 3.28084)


def _format_option_a(project: dict) -> dict:
    """
    Deterministic 4-field display card derived from raw permit metadata.
    No AI API call required.  Used as the fallback when Claude is unavailable.
    """
    impact_type = (project.get("impact_type") or "unknown").strip()
    address = (project.get("address") or "(unknown address)").strip()
    distance_m = project.get("distance_m")
    end_date = project.get("end_date")

    # --- distance string -------------------------------------------------
    distance_ft = _meters_to_feet(distance_m)
    distance_str = f"~{distance_ft:,} ft away" if distance_ft is not None else "nearby"

    # --- title -----------------------------------------------------------
    type_label = _IMPACT_TYPE_LABELS.get(impact_type, "Disruption")
    raw_title = f"{type_label} on {address}"
    display_title = raw_title if len(raw_title) <= 60 else raw_title[:57] + "\u2026"

    # --- description (factual one-liner) ---------------------------------
    end_str = f", active through {end_date}" if end_date else ""
    raw_desc = f"{type_label} at {address}{end_str}."
    description = raw_desc if len(raw_desc) <= 120 else raw_desc[:117] + "\u2026"

    # --- why it matters --------------------------------------------------
    why_it_matters = _WHY_IT_MATTERS_MAP.get(
        impact_type,
        "This signal contributes to the overall disruption risk for this address.",
    )

    return {
        "title": display_title,
        "distance": distance_str,
        "description": description,
        "why_it_matters": why_it_matters,
    }


# ---------------------------------------------------------------------------
# Claude API prompt templates
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You rewrite raw municipal permit and street-closure metadata into "
    "concise, plain-English signal cards for a real-estate livability app. "
    "Always respond with valid JSON only — no markdown fences, no commentary."
)

_USER_TEMPLATE = """\
Rewrite this disruption signal into a 4-field display card.

Metadata:
  impact_type : {impact_type}
  raw_title   : {raw_title}
  street      : {street}
  distance_ft : {distance_ft}
  start_date  : {start_date}
  end_date    : {end_date}
  source      : {source}

Rules:
  - title: ≤60 chars, title-case, no permit codes, starts with an action noun.
    Good examples: "Lane closure on Ohio St"
                   "Construction permit on N Damen Ave"
                   "Full street closure on W Grand Ave"
  - distance: exactly "~N,NNN ft away" (use the distance_ft value above).
    Example: "~1,100 ft away"
  - description: ≤120 chars, one complete sentence, plain English.
    Include the street name and address range if present; include end_date
    phrased as "active through <Month Day>" if present.
    Example: "Permitted construction closing a lane on Ohio between #1312–1313, active through April 10."
  - why_it_matters: ≤120 chars, one sentence about the practical impact.
    Example: "This closure may affect street parking and access on nearby blocks."
  - Never include raw permit codes, source IDs, or system-internal names.

Return exactly this JSON (no other text):
{{"title": "<title>", "distance": "<distance>", "description": "<description>", "why_it_matters": "<why_it_matters>"}}
"""


def _extract_json(text: str) -> str:
    """Pull the first {...} block from text (strips markdown fences if present)."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    return match.group(0) if match else text


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------


def _call_claude(project: dict) -> dict:
    """
    Call the Claude API to generate a 4-field display card for one signal.

    Returns {"title": str, "distance": str, "description": str, "why_it_matters": str}.
    Raises on API or JSON parse failure (caller catches and falls back to Option A).
    """
    import anthropic  # lazy import — only needed when key is set

    client = anthropic.Anthropic()

    distance_ft = _meters_to_feet(project.get("distance_m"))
    prompt = _USER_TEMPLATE.format(
        impact_type=project.get("impact_type") or "unknown",
        raw_title=project.get("title") or "(no title)",
        street=project.get("address") or "(unknown address)",
        distance_ft=f"{distance_ft:,} ft" if distance_ft is not None else "unknown",
        start_date=project.get("start_date") or "unknown",
        end_date=project.get("end_date") or "not specified",
        source=project.get("source") or "unknown",
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=384,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = next(
        (b.text for b in response.content if b.type == "text"), "{}"
    ).strip()

    parsed = json.loads(_extract_json(raw_text))
    return {
        "title": str(parsed.get("title", "")).strip(),
        "distance": str(parsed.get("distance", "")).strip(),
        "description": str(parsed.get("description", "")).strip(),
        "why_it_matters": str(parsed.get("why_it_matters", "")).strip(),
    }


# ---------------------------------------------------------------------------
# DB cache helpers — signal_display table (data-043)
# ---------------------------------------------------------------------------


def _load_display_cache(project_id: str, conn) -> Optional[dict]:
    """
    Return cached signal_display record for project_id, or None if not found.
    Rolls back on any DB error so the caller's connection stays usable.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT display_title, distance, description, why_it_matters
                FROM signal_display
                WHERE project_id = %s
                """,
                (project_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "title": row[0],
                    "distance": row[1],
                    "description": row[2],
                    "why_it_matters": row[3],
                }
    except Exception as exc:
        log.debug("signal_display cache read skipped project_id=%s: %s", project_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass
    return None


def _store_display_cache(project_id: str, display: dict, conn) -> None:
    """
    Persist a signal_display record. Non-fatal if the table does not exist yet.
    Rolls back on error so the caller's connection stays usable.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signal_display
                    (project_id, display_title, distance, description, why_it_matters)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (project_id) DO UPDATE
                    SET display_title  = EXCLUDED.display_title,
                        distance       = EXCLUDED.distance,
                        description    = EXCLUDED.description,
                        why_it_matters = EXCLUDED.why_it_matters,
                        updated_at     = now()
                """,
                (
                    project_id,
                    display["title"],
                    display["distance"],
                    display["description"],
                    display["why_it_matters"],
                ),
            )
            conn.commit()
    except Exception as exc:
        log.debug("signal_display cache write skipped project_id=%s: %s", project_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# DB cache helpers — signal_rewrites table (data-042, kept for migration reads)
# ---------------------------------------------------------------------------


def _load_rewrites_cache(project_id: str, conn) -> Optional[dict]:
    """
    Read the legacy signal_rewrites cache (data-042).
    Used as a secondary fallback if signal_display has no row yet.
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
            if row and row[0]:
                return {"title": row[0], "description": row[1]}
    except Exception as exc:
        log.debug("signal_rewrites cache read skipped project_id=%s: %s", project_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_top_risk_details(details: list[dict], conn) -> list[dict]:
    """
    Add display_title, distance, description, and why_it_matters to each
    top_risk_detail dict using the 4-field signal display card (data-043).

    Strategy (cache-first):
      1. Look up project_id in signal_display cache table.
      2. On miss: call Claude API, persist result to cache.
      3. On Claude failure: run Option A deterministic formatter.
      4. Never raises — graceful degradation at every step.

    Also adds rewritten_title and rewritten_description for backward compat
    with frontend code written before data-043.

    If ANTHROPIC_API_KEY is not set or the anthropic package is not installed,
    all signals go through the Option A formatter (no API call, no delay).

    Args:
        details: List of top_risk_detail dicts from compute_score().
        conn:    Open psycopg2 connection used for cache reads/writes.
                 Pass None to skip all DB cache operations.

    Returns:
        Same list with display_title, distance, description, why_it_matters,
        rewritten_title, and rewritten_description added to each item.
    """
    if not details:
        return details

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    use_claude = bool(api_key)

    if use_claude:
        try:
            import anthropic  # noqa: F401 — verify package available before looping
        except ImportError:
            log.warning("anthropic package not installed — using Option A formatter for all signals")
            use_claude = False

    enriched = []
    for detail in details:
        project_id = detail.get("project_id", "")
        display: dict = {}

        try:
            # 1. Check signal_display cache
            if project_id and conn:
                cached = _load_display_cache(project_id, conn)
                if cached:
                    display = cached
                    log.debug("signal_display cache_hit project_id=%s", project_id)

            # 2. Call Claude API on cache miss
            if not display and use_claude:
                try:
                    display = _call_claude(detail)
                    log.info(
                        "signal_display claude_call project_id=%s title=%r",
                        project_id,
                        display.get("title"),
                    )
                    if project_id and conn:
                        _store_display_cache(project_id, display, conn)
                except Exception as claude_exc:
                    log.warning(
                        "signal_display claude_call failed project_id=%s error=%s"
                        " — falling back to Option A",
                        project_id,
                        claude_exc,
                    )
                    display = {}

            # 3. Option A fallback
            if not display:
                display = _format_option_a(detail)
                log.debug("signal_display option_a project_id=%s", project_id)
                # Cache Option A results too so the API isn't called redundantly
                # on the next request. (Option A is cheap; caching it avoids
                # repeatedly computing the same string for the same project.)
                if project_id and conn and not use_claude:
                    _store_display_cache(project_id, display, conn)

        except Exception as exc:
            log.warning(
                "signal_display enrichment failed project_id=%s error=%s"
                " — using Option A",
                project_id,
                exc,
            )
            display = _format_option_a(detail)

        enriched.append(
            {
                **detail,
                # data-043 rich display fields
                "display_title": display.get("title") or None,
                "distance": display.get("distance") or None,
                "description": display.get("description") or None,
                "why_it_matters": display.get("why_it_matters") or None,
                # data-042 backward-compat aliases
                "rewritten_title": display.get("title") or None,
                "rewritten_description": display.get("description") or None,
            }
        )

    return enriched


_MAP_OVERRUN_HINTS: dict[str, str] = {
    "closure_full": "historically often extend by ~1–3 days",
    "closure_multi_lane": "historically often extend by ~1–2 days",
    "closure_single_lane": "historically can run ~0–1 day over plan",
    "construction": "historically can slip by ~3–7 days",
    "road_construction": "historically can slip by ~4–10 days",
}


def _map_signal_hash(signals: list[dict], interaction_type: str) -> str:
    """
    Stable hash for map-narration caching.
    Key requirement is (address, signal_ids_hash); we derive an ID from the
    rendered signal payload because nearby_signals currently has no explicit id.
    """
    tokens: list[str] = []
    for s in signals:
        tokens.append(
            "|".join(
                [
                    str(s.get("impact_type") or ""),
                    f"{float(s.get('lat', 0.0)):.5f}",
                    f"{float(s.get('lon', 0.0)):.5f}",
                    str(s.get("title") or ""),
                    str(s.get("source") or ""),
                ]
            )
        )
    payload = interaction_type + "||" + "||".join(sorted(tokens))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _call_claude_map_narrator(prompt: str) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    import anthropic  # lazy import

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=os.environ.get("CLAUDE_REWRITE_MODEL", _MODEL),
        max_tokens=180,
        temperature=0.2,
        system=(
            "You write concise municipal-risk map narration for Chicago. "
            "Return plain text only, 2-3 sentences, no markdown."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    text = " ".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    ).strip()
    return text or None


def get_map_narration(
    *,
    address: str,
    signals: list[dict],
    interaction_type: str,
    top_signal_title: str,
    calmer_direction: str,
    clicked_signal: Optional[dict],
    original_score: Optional[int],
    current_score: Optional[int],
    conn,
) -> Optional[str]:
    """
    Claude-powered map narrator with DB caching in signal_display.
    Cache key is derived from (address, signal_ids_hash).
    Returns None on any failure (caller should fail silently).
    """
    if not signals:
        return None

    signal_hash = _map_signal_hash(signals, interaction_type)
    cache_key = f"map_narrator::{address.strip().lower()}::{signal_hash}"

    try:
        if conn:
            cached = _load_display_cache(cache_key, conn)
            if cached and cached.get("description"):
                return cached["description"]
    except Exception:
        pass

    signal_count = len(signals)
    click_payload = ""
    if clicked_signal:
        impact = clicked_signal.get("impact_type", "signal")
        overrun_hint = _MAP_OVERRUN_HINTS.get(impact)
        overrun_line = (
            f"Include this overrun context if appropriate: {overrun_hint}."
            if overrun_hint else
            "No overrun data is available for this signal type; do not invent one."
        )
        click_payload = (
            f"\nClicked signal title: {clicked_signal.get('title')}\n"
            f"Clicked signal type: {impact}\n"
            f"Clicked signal dates: {clicked_signal.get('start_date')} to {clicked_signal.get('end_date')}\n"
            f"{overrun_line}\n"
        )

    pan_payload = ""
    if interaction_type == "map_pan" and original_score is not None and current_score is not None:
        delta = current_score - original_score
        pan_payload = (
            f"\nOriginal score: {original_score}. New area score: {current_score}. "
            f"Difference: {delta:+d}. Explicitly compare them in plain English.\n"
        )

    prompt = (
        f"Address: {address}\n"
        f"Interaction type: {interaction_type}\n"
        f"Active signals within 500m: {signal_count}\n"
        f"Top signal plain title: {top_signal_title}\n"
        f"Calmer direction from searched address: {calmer_direction}\n"
        f"{click_payload}"
        f"{pan_payload}"
        "Write 2-3 concise sentences. For default interaction, use this framing: "
        "'This block has [N] active disruptions within 500m. The most significant is "
        "[top signal plain title]. The area to the [direction] is notably calmer if "
        "you have flexibility.' Keep it natural and non-alarmist."
    )

    try:
        narration = _call_claude_map_narrator(prompt)
        if not narration:
            return None
        if conn:
            _store_display_cache(
                cache_key,
                {
                    "title": "Map narrator",
                    "distance": "",
                    "description": narration,
                    "why_it_matters": "map_narrator_cache",
                },
                conn,
            )
        return narration
    except Exception:
        return None
