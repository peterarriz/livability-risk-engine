"""
backend/models/project.py
tasks: data-006, data-007
lane: data

Canonical Project model and normalization functions.

Converts raw building permit and street closure records into the
canonical Project shape used by the scoring engine and API.

The normalization logic maps source fields to the impact_type
classification defined in docs/03_scoring_model.md, which directly
controls base weight assignment in the scoring engine.

Usage (standalone test):
  python backend/models/project.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Canonical project dataclass
# Mirrors the `projects` table in db/schema.sql.
# ---------------------------------------------------------------------------

@dataclass
class Project:
    """
    Canonical project record for the scoring engine.
    All source types (permits, closures) normalize into this shape.
    """

    project_id: str          # stable display ID: "source:source_id"
    source: str              # 'chicago_permits' | 'chicago_closures' | 'idot_road_projects' | 'cook_county_permits'
    source_id: str           # original record key

    # Classification — drives base weight in scoring engine
    # Valid: closure_full | closure_multi_lane | closure_single_lane |
    #        demolition | construction | light_permit
    impact_type: str

    title: str               # short human-readable label
    notes: Optional[str]     # additional context for top_risks display

    start_date: Optional[date]
    end_date: Optional[date]
    status: str              # active | planned | completed | unknown

    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    severity_hint: str       # HIGH | MEDIUM | LOW


# ---------------------------------------------------------------------------
# Impact type constants
# Aligns with docs/03_scoring_model.md base weight table.
# ---------------------------------------------------------------------------

IMPACT_FULL_CLOSURE     = "closure_full"
IMPACT_MULTI_LANE       = "closure_multi_lane"
IMPACT_SINGLE_LANE      = "closure_single_lane"
IMPACT_DEMOLITION       = "demolition"
IMPACT_CONSTRUCTION     = "construction"
IMPACT_ROAD_CONSTRUCTION = "road_construction"
IMPACT_LIGHT_PERMIT     = "light_permit"
IMPACT_UTILITY_OUTAGE   = "utility_outage"   # data-046: active infrastructure emergency
IMPACT_UTILITY_REPAIR   = "utility_repair"

# Base weights per docs/03_scoring_model.md
BASE_WEIGHTS: dict[str, int] = {
    IMPACT_FULL_CLOSURE:  45,
    IMPACT_MULTI_LANE:    38,
    IMPACT_SINGLE_LANE:   28,
    IMPACT_DEMOLITION:    24,
    IMPACT_UTILITY_OUTAGE:    25,
    IMPACT_CONSTRUCTION:      16,
    IMPACT_ROAD_CONSTRUCTION: 20,
    IMPACT_UTILITY_REPAIR:    15,
    IMPACT_LIGHT_PERMIT:       8,
}

# Severity hints derived from impact type for normalization pre-computation.
IMPACT_SEVERITY: dict[str, str] = {
    IMPACT_FULL_CLOSURE:  "HIGH",
    IMPACT_MULTI_LANE:    "HIGH",
    IMPACT_SINGLE_LANE:   "MEDIUM",
    IMPACT_DEMOLITION:    "HIGH",
    IMPACT_UTILITY_OUTAGE:    "HIGH",
    IMPACT_CONSTRUCTION:      "MEDIUM",
    IMPACT_ROAD_CONSTRUCTION: "MEDIUM",
    IMPACT_UTILITY_REPAIR:    "MEDIUM",
    IMPACT_LIGHT_PERMIT:      "LOW",
}


# ---------------------------------------------------------------------------
# Building permit normalization  (data-006)
# ---------------------------------------------------------------------------

# Keywords in work_description or permit_type that signal higher-weight types.
_DEMOLITION_TERMS = re.compile(
    r"\b(demolition|demo|wreck|raze|tear.?down|excavat|excavation)\b",
    re.IGNORECASE,
)

_HEAVY_CONSTRUCTION_TERMS = re.compile(
    r"\b(foundation|structural|new.?construction|erect|erection|"
    r"high.?rise|multi.?story|excavat)\b",
    re.IGNORECASE,
)

_PERMIT_TYPE_DEMOLITION = re.compile(
    r"\b(PERMIT - WRECKING/DEMOLITION)\b",
    re.IGNORECASE,
)

_PERMIT_TYPE_RENOVATION = re.compile(
    r"\b(PERMIT - EASY PERMIT PROGRAM|PERMIT - SIGNS)\b",
    re.IGNORECASE,
)


def _classify_permit(permit_type: str, work_description: str) -> str:
    """
    Assign an impact_type to a building permit record.

    Priority order:
    1. Demolition permit type
    2. Demolition keywords in work description
    3. Heavy construction keywords
    4. Active building permit
    5. Light permit (default)

    Returns one of the IMPACT_* constants.
    """
    pt = (permit_type or "").strip()
    wd = (work_description or "").strip()

    if _PERMIT_TYPE_DEMOLITION.search(pt):
        return IMPACT_DEMOLITION

    if _DEMOLITION_TERMS.search(wd) or _DEMOLITION_TERMS.search(pt):
        return IMPACT_DEMOLITION

    if _HEAVY_CONSTRUCTION_TERMS.search(wd):
        return IMPACT_CONSTRUCTION

    if pt and not _PERMIT_TYPE_RENOVATION.search(pt):
        return IMPACT_CONSTRUCTION

    return IMPACT_LIGHT_PERMIT


def _parse_date(value: str | None) -> Optional[date]:
    """Parse a Socrata date string to a Python date. Returns None on failure."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:len(fmt) + 2], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _build_address(record: dict) -> str:
    """Assemble a normalized address string from raw permit fields."""
    parts = [
        record.get("street_number", ""),
        record.get("street_direction", ""),
        record.get("street_name", ""),
        record.get("suffix", ""),
    ]
    address = " ".join(p.strip() for p in parts if p and p.strip())
    return f"{address}, Chicago, IL" if address else "Chicago, IL"


def _permit_status(record: dict) -> str:
    """
    Derive a normalized status from permit dates.
    Without a work-complete date, assume active if issue_date is set.
    """
    issue = _parse_date(record.get("issue_date"))
    expiry = _parse_date(record.get("expiration_date"))
    today = date.today()

    if expiry and expiry < today:
        return "completed"
    if issue:
        return "active"
    return "unknown"


def normalize_permit(record: dict) -> Project:
    """
    Normalize a raw building permit record into a canonical Project.

    Args:
        record: A single dict from the raw_building_permits staging file.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = record.get("permit_", "") or record.get("source_id", "")
    permit_type = record.get("permit_type", "")
    work_desc = record.get("work_description", "")

    impact_type = _classify_permit(permit_type, work_desc)

    # Title: short human-readable label for top_risks display.
    title_parts = []
    if permit_type:
        # Strip the "PERMIT - " prefix for brevity.
        short_type = re.sub(r"^PERMIT\s*-\s*", "", permit_type, flags=re.IGNORECASE).strip()
        title_parts.append(short_type)

    address_str = _build_address(record)
    if address_str != "Chicago, IL":
        title_parts.append(f"at {address_str}")

    title = " ".join(title_parts) if title_parts else f"Building permit {source_id}"

    notes = work_desc[:200] if work_desc else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    return Project(
        project_id=f"chicago_permits:{source_id}",
        source="chicago_permits",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("issue_date")),
        end_date=_parse_date(record.get("expiration_date")),
        status=_permit_status(record),
        address=address_str,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Street closure normalization  (data-007)
# ---------------------------------------------------------------------------

# Closure type keywords that indicate full or multi-lane closures.
# Aligns with the base weight table in docs/03_scoring_model.md.
_FULL_CLOSURE_TERMS = re.compile(
    r"\b(full.?street|full.?closure|both.?direction|all.?lane|road.?closure|"
    r"street.?closed|closed.?to.?traffic)\b",
    re.IGNORECASE,
)

_MULTI_LANE_TERMS = re.compile(
    r"\b(multi.?lane|multiple.?lane|two.?lane|2.?lane|both.?lane|"
    r"major.?closure|major.?work)\b",
    re.IGNORECASE,
)

_SINGLE_LANE_TERMS = re.compile(
    r"\b(single.?lane|one.?lane|1.?lane|curb.?lane|parking.?lane|"
    r"shoulder|sidewalk|pedestrian)\b",
    re.IGNORECASE,
)


def _classify_closure(work_type: str, street_closure_type: str, closure_reason: str) -> str:
    """
    Assign an impact_type to a street closure record.

    Uses a priority-ordered keyword match across the three most informative
    source fields. Street closures are the highest-weight inputs to the
    scoring model, so erring toward higher classification is preferred
    over under-classifying.

    Returns one of the IMPACT_* constants.
    """
    combined = " ".join([
        work_type or "",
        street_closure_type or "",
        closure_reason or "",
    ])

    if _FULL_CLOSURE_TERMS.search(combined):
        return IMPACT_FULL_CLOSURE

    if _MULTI_LANE_TERMS.search(combined):
        return IMPACT_MULTI_LANE

    if _SINGLE_LANE_TERMS.search(combined):
        return IMPACT_SINGLE_LANE

    # Default for unclassified closures: single-lane weight is conservative
    # but avoids over-counting vague records.
    return IMPACT_SINGLE_LANE


def _closure_status(record: dict) -> str:
    """Derive normalized status from closure source status and dates."""
    src_status = (record.get("status") or "").lower()
    today = date.today()

    # Trust explicit source status first.
    if "cancel" in src_status or "revok" in src_status:
        return "completed"
    if "complet" in src_status:
        return "completed"

    start = _parse_date(record.get("start_date"))
    end = _parse_date(record.get("end_date"))

    if end and end < today:
        return "completed"
    if start and start > today:
        return "planned"
    if start:
        return "active"

    return "unknown"


def _closure_title(record: dict) -> str:
    """Build a short human-readable title for a closure record."""
    parts = []

    street = record.get("street_name", "").strip()
    from_st = record.get("from_street", "").strip()
    to_st = record.get("to_street", "").strip()

    if street:
        parts.append(street)
    if from_st and to_st:
        parts.append(f"from {from_st} to {to_st}")
    elif from_st:
        parts.append(f"near {from_st}")

    # Prefer the human-readable description over the raw work_type code.
    # work_type_description is mapped from Socrata's `worktypedescription` field
    # and contains plain English (e.g. "General Opening" vs. "GenOpening").
    work_type_desc = record.get("work_type_description", "").strip()
    work_type = record.get("work_type", "").strip()
    work_label = work_type_desc or work_type
    if work_label:
        parts.append(f"({work_label})")

    if parts:
        return " ".join(parts) + " closure"

    source_id = record.get("row_id", record.get("source_id", ""))
    return f"Street closure {source_id}"


def normalize_closure(record: dict) -> Project:
    """
    Normalize a raw street closure record into a canonical Project.

    Args:
        record: A single dict from the raw_street_closures staging file.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = record.get("row_id", "") or record.get("source_id", "")
    work_type = record.get("work_type", "")
    closure_type = record.get("street_closure_type", "")
    closure_reason = record.get("closure_reason", "")

    impact_type = _classify_closure(work_type, closure_type, closure_reason)

    title = _closure_title(record)

    notes_parts = []
    if closure_type:
        notes_parts.append(closure_type)
    if closure_reason:
        notes_parts.append(closure_reason)
    notes = "; ".join(notes_parts)[:200] if notes_parts else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    # Try to extract lat/lon from nested location dict if top-level is absent.
    if (lat is None or lon is None) and isinstance(record.get("location"), dict):
        loc = record["location"]
        lat = _safe_float(loc.get("latitude"))
        lon = _safe_float(loc.get("longitude"))

    # Build address string from street fields.
    street_parts = [
        record.get("street_direction", ""),
        record.get("street_name", ""),
    ]
    address_str_parts = [p.strip() for p in street_parts if p and p.strip()]
    address_str = (
        f"{' '.join(address_str_parts)}, Chicago, IL"
        if address_str_parts
        else "Chicago, IL"
    )

    return Project(
        project_id=f"chicago_closures:{source_id}",
        source="chicago_closures",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("start_date")),
        end_date=_parse_date(record.get("end_date")),
        status=_closure_status(record),
        address=address_str,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# IDOT road project normalization  (data-031)
# ---------------------------------------------------------------------------

_IDOT_BRIDGE_TERMS = re.compile(
    r"\b(bridge|overpass|viaduct|underpass|culvert)\b",
    re.IGNORECASE,
)

_IDOT_RECONSTRUCTION_TERMS = re.compile(
    r"\b(reconstruction|reconstruct|rebuilding|rebuild|resurfacing|resurface|"
    r"full.?depth|fdr|mill.?and.?overlay|widening|interchange)\b",
    re.IGNORECASE,
)

_IDOT_MAINTENANCE_TERMS = re.compile(
    r"\b(patching|crack.?seal|joint.?repair|guardrail|signage|pavement.?marking|"
    r"landscaping|lighting|signal|striping)\b",
    re.IGNORECASE,
)


def _classify_idot_project(work_type: str, description: str) -> str:
    """
    Assign an impact_type to an IDOT road project.

    Priority order:
    1. Bridge/overpass work (high disruption)
    2. Reconstruction/resurfacing (medium-high disruption)
    3. Maintenance items (low disruption)
    4. Default: construction

    Returns one of the IMPACT_* constants.
    """
    combined = " ".join([work_type or "", description or ""])

    if _IDOT_BRIDGE_TERMS.search(combined):
        return IMPACT_CONSTRUCTION  # Bridges close lanes but rarely full streets

    if _IDOT_RECONSTRUCTION_TERMS.search(combined):
        return IMPACT_CONSTRUCTION

    if _IDOT_MAINTENANCE_TERMS.search(combined):
        return IMPACT_LIGHT_PERMIT

    return IMPACT_CONSTRUCTION


def _idot_status(record: dict) -> str:
    """Derive normalized status from IDOT project dates and status field."""
    src_status = (record.get("status") or "").lower()
    today = date.today()

    if "complet" in src_status or "close" in src_status:
        return "completed"
    if "cancel" in src_status:
        return "completed"

    start = _parse_date(record.get("start_date"))
    end = _parse_date(record.get("end_date"))

    if end and end < today:
        return "completed"
    if start and start > today:
        return "planned"
    if start:
        return "active"

    return "unknown"


def _idot_address(record: dict) -> str:
    """Build an address string from IDOT route and county fields."""
    route = (record.get("route") or "").strip()
    county = (record.get("county") or "").strip()

    parts = []
    if route:
        parts.append(route)
    if county:
        parts.append(f"{county} County")
    parts.append("IL")

    return ", ".join(parts) if parts else "Illinois"


def normalize_idot_project(record: dict) -> Project:
    """
    Normalize a raw IDOT road project record into a canonical Project.

    Args:
        record: A single dict from the raw_idot_road_projects staging file.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    # ArcGIS data uses row_id (int) and contract_number; Socrata used project_number.
    source_id = str(
        record.get("row_id")
        or record.get("contract_number")
        or record.get("project_number")
        or record.get("source_id")
        or ""
    )
    construction_type = record.get("construction_type", "") or ""
    lanes_closed = record.get("lanes_ramps_closed", "") or ""
    impact_on_travel = record.get("impact_on_travel", "") or ""
    # For classification, combine construction_type with any description field.
    work_type = construction_type or record.get("work_type", "") or ""
    description = (
        record.get("location", "")  # ArcGIS "location" is a description string
        or record.get("project_description", "")
        or ""
    )

    impact_type = _classify_idot_project(work_type, description)

    # Title: route + location for human-readable display.
    route = (record.get("route") or "").strip()
    location = (record.get("location") or "").strip() if isinstance(record.get("location"), str) else ""
    near_town = (record.get("near_town") or "").strip()
    title_parts = []
    if route:
        title_parts.append(f"Route {route}")
    if location:
        title_parts.append(location)
    elif near_town:
        title_parts.append(f"near {near_town}")
    title = " — ".join(title_parts) if title_parts else f"IDOT project {source_id}"

    # Notes: combine construction type, closure info, and detour.
    notes_parts = []
    if construction_type:
        notes_parts.append(construction_type)
    if lanes_closed:
        notes_parts.append(f"Lanes/ramps closed: {lanes_closed}")
    detour = record.get("detour_route") or ""
    if detour:
        notes_parts.append(f"Detour: {detour}")
    notes = "; ".join(notes_parts)[:200] if notes_parts else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    # Address from location + near_town (ArcGIS doesn't provide street addresses).
    if location and near_town:
        address_str = f"{location}, {near_town}, IL"
    elif location:
        address_str = f"{location}, IL"
    elif near_town:
        address_str = f"{near_town}, IL"
    else:
        address_str = _idot_address(record)

    return Project(
        project_id=f"idot_road:{source_id}",
        source="idot_road_construction",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("start_date")),
        end_date=_parse_date(record.get("end_date")),
        status=_idot_status(record),
        address=address_str,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Illinois city / Cook County permit normalization  (data-033)
# ---------------------------------------------------------------------------
# Handles permits from Cook County and additional IL cities ingested via
# backend/ingest/il_city_permits.py.  Field names have already been mapped
# to a consistent internal schema by normalize_raw_record() in that module.

def normalize_il_city_permit(record: dict) -> Project:
    """
    Normalize a pre-mapped Illinois city/county permit record into a
    canonical Project.

    Args:
        record: A dict produced by il_city_permits.normalize_raw_record().
                Keys are always the internal field names (source_key, city_name,
                source_id, permit_type, description, issue_date, …).

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_key = record.get("source_key", "il_city")
    city_name  = record.get("city_name", "Illinois")
    source_id  = record.get("source_id", "")

    permit_type = record.get("permit_type", "") or ""
    description = record.get("description", "") or ""

    impact_type = _classify_permit(permit_type, description)

    # Title: strip "PERMIT - " prefix for brevity, append city if useful.
    short_type = re.sub(r"^PERMIT\s*-\s*", "", permit_type, flags=re.IGNORECASE).strip()
    address_raw = (record.get("address") or "").strip()
    address_str = f"{address_raw}, {record.get('city_il', city_name + ', IL')}" if address_raw else f"{city_name}, IL"

    title_parts = []
    if short_type:
        title_parts.append(short_type)
    if address_raw:
        title_parts.append(f"at {address_raw}")
    title = " ".join(title_parts) if title_parts else f"{city_name} permit {source_id}"

    notes = description[:200] if description else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    return Project(
        project_id=f"{source_key}:{source_id}",
        source=source_key,
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("issue_date")),
        end_date=_parse_date(record.get("expiration_date")),
        status=_permit_status(record),
        address=address_str,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# US city permit normalization  (data-038)
# ---------------------------------------------------------------------------
# Handles permits from the top 10 US cities ingested via
# backend/ingest/us_city_permits.py.  Field names have already been mapped
# to a consistent internal schema by normalize_raw_record() in that module.
# The normalized record format is identical to il_city_permits records, so
# this function mirrors normalize_il_city_permit() with city_state support.

def normalize_us_city_permit(record: dict) -> Project:
    """
    Normalize a pre-mapped US city permit record into a canonical Project.

    Args:
        record: A dict produced by us_city_permits.normalize_raw_record().
                Keys are always the internal field names (source_key, city_name,
                city_state, source_id, permit_type, description, issue_date, …).

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_key = record.get("source_key", "us_city")
    city_name  = record.get("city_name", "US City")
    source_id  = record.get("source_id", "")

    permit_type = record.get("permit_type", "") or ""
    description = record.get("description", "") or ""

    impact_type = _classify_permit(permit_type, description)

    short_type = re.sub(r"^PERMIT\s*-\s*", "", permit_type, flags=re.IGNORECASE).strip()
    address_raw = (record.get("address") or "").strip()
    city_state = record.get("city_state", city_name)
    address_str = f"{address_raw}, {city_state}" if address_raw else city_state

    title_parts = []
    if short_type:
        title_parts.append(short_type)
    if address_raw:
        title_parts.append(f"at {address_raw}")
    title = " ".join(title_parts) if title_parts else f"{city_name} permit {source_id}"

    notes = description[:200] if description else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    return Project(
        project_id=f"{source_key}:{source_id}",
        source=source_key,
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("issue_date")),
        end_date=_parse_date(record.get("expiration_date")),
        status=_permit_status(record),
        address=address_str,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# CTA service alert normalization  (data-034)
# ---------------------------------------------------------------------------
# Handles alerts ingested via backend/ingest/cta_alerts.py.
# Alerts are filtered for planned/upcoming service changes (track work,
# station closures, reroutes due to construction).

_CTA_NO_SERVICE = re.compile(
    r"\b(no service|out of service|suspended)\b",
    re.IGNORECASE,
)

_CTA_REDUCED = re.compile(
    r"\b(reduced|limited|shuttle|single.?track|delay)\b",
    re.IGNORECASE,
)

_CTA_CONSTRUCTION = re.compile(
    r"\b(planned|construction|track.?work|maintenance|renovation|"
    r"rebuild|replacement|station.?clos)\b",
    re.IGNORECASE,
)


def _classify_cta_alert(impact: str, headline: str) -> str:
    """
    Assign an impact_type to a CTA service alert.

    Priority order:
    1. No service / suspended → closure_full
    2. Reduced / shuttle / single-track → closure_single_lane
    3. Planned work / construction keywords → construction
    4. Default → light_permit
    """
    combined = f"{impact} {headline}"

    if _CTA_NO_SERVICE.search(combined):
        return IMPACT_FULL_CLOSURE

    if _CTA_REDUCED.search(combined):
        return IMPACT_SINGLE_LANE

    if _CTA_CONSTRUCTION.search(combined):
        return IMPACT_CONSTRUCTION

    return IMPACT_LIGHT_PERMIT


def _cta_alert_status(record: dict) -> str:
    """Derive normalized status from CTA alert dates."""
    is_tbd = record.get("is_tbd", "0") == "1"
    today = date.today()

    start = _parse_date(record.get("event_start"))
    end   = None if is_tbd else _parse_date(record.get("event_end"))

    if end and end < today:
        return "completed"
    if start and start > today:
        return "planned"
    if start:
        return "active"

    return "unknown"


def normalize_cta_alert(record: dict) -> Project:
    """
    Normalize a CTA service alert record into a canonical Project.

    Args:
        record: A dict produced by cta_alerts.normalize_alert().
                Keys are the internal field names (alert_id, headline,
                impact, event_start, event_end, address, ...).

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = record.get("alert_id", "")
    impact    = record.get("impact", "") or ""
    headline  = record.get("headline", "") or ""

    impact_type = _classify_cta_alert(impact, headline)

    # Title: use headline truncated for display.
    title = headline[:150] if headline else f"CTA alert {source_id}"

    # Notes: combine short description + location.
    notes_parts = []
    short_desc = (record.get("short_description") or "").strip()
    if short_desc:
        notes_parts.append(short_desc)
    service_loc = (record.get("service_location") or "").strip()
    if service_loc:
        notes_parts.append(f"Location: {service_loc}")
    notes = "; ".join(notes_parts)[:200] if notes_parts else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    address = (record.get("address") or "").strip() or "Chicago, IL"

    return Project(
        project_id=f"cta_alert:{source_id}",
        source="cta_alerts",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("event_start")),
        end_date=_parse_date(record.get("event_end")),
        status=_cta_alert_status(record),
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Chicago traffic crash normalization  (data-035)
# ---------------------------------------------------------------------------
# Handles crashes ingested via backend/ingest/chicago_traffic_crashes.py.
# Recent crash scenes (last N days) represent active disruption zones.

_CRASH_FATAL = re.compile(
    r"\b(fatal|fatality)\b",
    re.IGNORECASE,
)

_CRASH_INCAPACITATING = re.compile(
    r"\b(incapacitat)\b",
    re.IGNORECASE,
)

_CRASH_INJURY_OR_TOW = re.compile(
    r"\b(injury|tow)\b",
    re.IGNORECASE,
)


def _classify_crash(crash_type: str, most_severe_injury: str) -> str:
    """
    Assign an impact_type to a traffic crash record.

    Priority order:
    1. Fatal injury → closure_full
    2. Incapacitating injury → closure_multi_lane
    3. Any injury or tow-required → construction
    4. Default → light_permit
    """
    combined = f"{crash_type} {most_severe_injury}"

    if _CRASH_FATAL.search(combined) or most_severe_injury.strip().upper() == "FATAL":
        return IMPACT_FULL_CLOSURE

    if _CRASH_INCAPACITATING.search(combined):
        return IMPACT_MULTI_LANE

    if _CRASH_INJURY_OR_TOW.search(combined):
        return IMPACT_CONSTRUCTION

    return IMPACT_LIGHT_PERMIT


def normalize_traffic_crash(record: dict) -> Project:
    """
    Normalize a raw traffic crash record into a canonical Project.

    Args:
        record: A single dict from the chicago_traffic_crashes staging file.
                Fields: crash_record_id, crash_date, crash_type,
                        most_severe_injury, injuries_total,
                        street_no, street_direction, street_name,
                        latitude, longitude.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = record.get("crash_record_id", "")
    crash_type = (record.get("crash_type") or "").strip()
    most_severe_injury = (record.get("most_severe_injury") or "").strip()

    impact_type = _classify_crash(crash_type, most_severe_injury)

    # Build address from street fields.
    addr_parts = [
        record.get("street_no", ""),
        record.get("street_direction", ""),
        record.get("street_name", ""),
    ]
    addr_str = " ".join(p.strip() for p in addr_parts if p and str(p).strip())
    address = f"{addr_str}, Chicago, IL" if addr_str else "Chicago, IL"

    # Title: type + location.
    short_type = crash_type or "Traffic crash"
    title = f"{short_type} at {addr_str}" if addr_str else short_type

    # Notes: injury severity + unit count.
    notes_parts = []
    if most_severe_injury:
        notes_parts.append(most_severe_injury)
    injuries = record.get("injuries_total")
    if injuries and str(injuries) not in ("0", "0.0", ""):
        notes_parts.append(f"Injuries: {injuries}")
    num_units = record.get("num_units")
    if num_units:
        notes_parts.append(f"Vehicles: {num_units}")
    notes = "; ".join(notes_parts)[:200] if notes_parts else None

    # Crash date as start. Treat disruption window as same-day (end = start).
    crash_date = _parse_date(record.get("crash_date"))

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    return Project(
        project_id=f"chicago_crash:{source_id}",
        source="chicago_traffic_crashes",
        source_id=source_id,
        impact_type=impact_type,
        title=title[:200],
        notes=notes,
        start_date=crash_date,
        end_date=crash_date,  # same-day event; loader status logic handles age
        status="active",      # crashes in the fetch window are considered active
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Divvy bike station closure normalization  (data-035)
# ---------------------------------------------------------------------------
# Handles out-of-service station records from chicago_divvy_stations.py.
# Station closures are LOW-severity (light_permit weight) disruption signals.

def normalize_divvy_station(record: dict) -> Project:
    """
    Normalize a Divvy out-of-service station record into a canonical Project.

    Args:
        record: A dict produced by chicago_divvy_stations.build_records().
                Keys: station_id, name, address, latitude, longitude,
                      is_installed, is_renting, is_returning, reason.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = str(record.get("station_id", ""))
    name      = (record.get("name") or f"Station {source_id}").strip()
    reason    = (record.get("reason") or "Station closed").strip()

    # Always light_permit — Divvy station closures are low disruption.
    impact_type = IMPACT_LIGHT_PERMIT

    title = f"{name} Divvy station closed"

    # Build address: prefer station address field; fallback to name + city.
    addr_raw = (record.get("address") or name).strip()
    address  = f"{addr_raw}, Chicago, IL" if addr_raw else "Chicago, IL"

    notes = reason[:200]

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    return Project(
        project_id=f"chicago_divvy:{source_id}",
        source="chicago_divvy",
        source_id=source_id,
        impact_type=impact_type,
        title=title[:200],
        notes=notes,
        start_date=None,
        end_date=None,
        status="active",
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Chicago 311 service request normalization  (data-036)
# ---------------------------------------------------------------------------
# Handles infrastructure disruption reports ingested via chicago_311_requests.py.
# Potholes, water main breaks, cave-ins, tree emergencies, and traffic signal
# outages are short-lived but active street hazards that affect traffic and
# pedestrian safety.

_311_WATER_MAIN = re.compile(
    r"\b(water.?main|water.?break|water.?leak|water.?service)\b",
    re.IGNORECASE,
)

_311_GAS_LEAK = re.compile(
    r"\b(gas.?leak|gas.?emergency|natural.?gas)\b",
    re.IGNORECASE,
)

_311_CAVE_IN = re.compile(
    r"\b(cave.?in|pavement.?cave|sinkhole)\b",
    re.IGNORECASE,
)

_311_TREE = re.compile(
    r"\b(tree.?emergency|tree.?down|pole.?down)\b",
    re.IGNORECASE,
)

_311_TRAFFIC_SIGNAL = re.compile(
    r"\btraffic.?signal.?out\b",
    re.IGNORECASE,
)


def _classify_311_request(sr_type: str) -> str:
    """
    Assign an impact_type to a 311 service request.

    Priority order:
    1. Water main break / gas leak → utility_outage (active infrastructure emergency)
    2. Cave-in → multi_lane (active lane blockage)
    3. Tree emergency / pole down → single lane (temporary obstruction)
    4. Pothole and others → light_permit (road degradation hazard)
    """
    sr = (sr_type or "").strip()

    if _311_WATER_MAIN.search(sr):
        return IMPACT_UTILITY_OUTAGE

    if _311_GAS_LEAK.search(sr):
        return IMPACT_UTILITY_OUTAGE

    if _311_CAVE_IN.search(sr):
        return IMPACT_MULTI_LANE

    if _311_TREE.search(sr):
        return IMPACT_SINGLE_LANE

    return IMPACT_LIGHT_PERMIT


def _311_status(record: dict) -> str:
    """Derive normalized status from 311 request status field."""
    status = (record.get("status") or "").lower()

    if "completed" in status or "closed" in status:
        return "completed"

    # 'Open - Dup' is a duplicate; treat as completed to avoid double-counting.
    if "dup" in status:
        return "completed"

    if "open" in status:
        return "active"

    return "unknown"


def normalize_311_request(record: dict) -> Project:
    """
    Normalize a raw 311 service request record into a canonical Project.

    Args:
        record: A single dict from the chicago_311_requests staging file.
                Fields: sr_number, sr_type, created_date, closed_date,
                        status, street_address, latitude, longitude.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id = record.get("sr_number", "")
    sr_type   = (record.get("sr_type") or "").strip()

    impact_type = _classify_311_request(sr_type)

    # Title: type + address.
    address_raw = (record.get("street_address") or "").strip()
    address = f"{address_raw}, Chicago, IL" if address_raw else "Chicago, IL"
    title = f"{sr_type} at {address_raw}" if address_raw else sr_type or f"311 request {source_id}"

    # Notes: sr_type if not in title.
    notes = sr_type[:200] if sr_type else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    created = _parse_date(record.get("created_date"))
    closed  = _parse_date(record.get("closed_date"))

    return Project(
        project_id=f"chicago_311:{source_id}",
        source="chicago_311_requests",
        source_id=source_id,
        impact_type=impact_type,
        title=title[:200],
        notes=notes,
        start_date=created,
        end_date=closed,
        status=_311_status(record),
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Chicago Film Permit normalization  (data-036)
# ---------------------------------------------------------------------------
# Handles film permits ingested via chicago_film_permits.py.
# Film shoots cause active street closures, no-parking zones, and
# temporary lane blockages. Impact level depends on permit type.

_FILM_MAJOR = re.compile(
    r"\b(feature|major|full.?street|road.?closure|parade|large)\b",
    re.IGNORECASE,
)

_FILM_TV = re.compile(
    r"\b(television|tv|series|episode|commercial|music.?video)\b",
    re.IGNORECASE,
)


def _classify_film_permit(permit_type: str) -> str:
    """
    Assign an impact_type to a film permit.

    Priority order:
    1. Feature / major production → single_lane (street parking + lane holds)
    2. TV / commercial → light_permit (smaller footprint)
    3. Default → light_permit
    """
    pt = (permit_type or "").strip()

    if _FILM_MAJOR.search(pt):
        return IMPACT_SINGLE_LANE

    if _FILM_TV.search(pt):
        return IMPACT_LIGHT_PERMIT

    return IMPACT_LIGHT_PERMIT


def _film_permit_status(record: dict) -> str:
    """Derive normalized status from film permit dates."""
    today = date.today()
    start = _parse_date(record.get("applicationstartdate") or record.get("startdate"))
    end   = _parse_date(record.get("applicationenddate") or record.get("enddate"))

    if end and end < today:
        return "completed"
    if start and start > today:
        return "planned"
    if start:
        return "active"
    return "unknown"


def normalize_film_permit(record: dict) -> Project:
    """
    Normalize a raw Chicago film permit record into a canonical Project.

    Args:
        record: A single dict from the chicago_film_permits staging file.
                Fields: id, startdate, enddate, permittype, streetname,
                        fromlocation, tolocation, community, latitude, longitude.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id   = str(record.get("applicationnumber") or record.get("id", ""))
    permit_type = (record.get("applicationtype") or record.get("permittype") or "").strip()
    street      = (record.get("streetname") or "").strip()
    direction   = (record.get("direction") or "").strip()
    from_loc    = str(record.get("streetnumberfrom") or record.get("fromlocation") or "").strip()
    to_loc      = str(record.get("streetnumberto") or record.get("tolocation") or "").strip()
    community   = (record.get("community") or "").strip()

    impact_type = _classify_film_permit(permit_type)

    # Title: permit type + street if available.
    title_parts = []
    if permit_type:
        title_parts.append(permit_type)
    if street:
        title_parts.append(f"on {street}")
        if from_loc and to_loc:
            title_parts.append(f"({from_loc} to {to_loc})")
    title = " ".join(title_parts) if title_parts else f"Film permit {source_id}"

    # Address: direction + street + community.
    addr_parts = []
    street_full = f"{direction} {street}".strip() if direction else street
    if street_full:
        addr_parts.append(street_full)
    if community:
        addr_parts.append(community)
    addr_parts.append("Chicago, IL")
    address = ", ".join(addr_parts)

    # Notes: cross streets for location context.
    notes = None
    if from_loc and to_loc:
        notes = f"From {from_loc} to {to_loc}"
    elif from_loc:
        notes = f"From {from_loc}"

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    start = _parse_date(record.get("applicationstartdate") or record.get("startdate"))
    end   = _parse_date(record.get("applicationenddate") or record.get("enddate"))

    return Project(
        project_id=f"chicago_film:{source_id}",
        source="chicago_film_permits",
        source_id=source_id,
        impact_type=impact_type,
        title=title[:200],
        notes=notes,
        start_date=start,
        end_date=end,
        status=_film_permit_status(record),
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Chicago Special Events Permit normalization  (data-036)
# ---------------------------------------------------------------------------
# Handles special event permits ingested via chicago_special_events.py.
# Large public events (festivals, parades, marathons) cause major traffic
# disruption and parking restrictions.

_EVENT_HIGH_IMPACT = re.compile(
    r"\b(parade|marathon|race|triathlon|festival|air.?show|"
    r"street.?closure|full.?closure|block.?party)\b",
    re.IGNORECASE,
)

_EVENT_MEDIUM_IMPACT = re.compile(
    r"\b(concert|fair|market|expo|run|walk|rally|demonstration)\b",
    re.IGNORECASE,
)


def _classify_special_event(event_type: str, event_name: str) -> str:
    """
    Assign an impact_type to a special event permit.

    Priority order:
    1. Parade / marathon / major street closure → multi_lane
    2. Concert / fair / organized run → single_lane
    3. Default → light_permit
    """
    combined = f"{event_type} {event_name}"

    if _EVENT_HIGH_IMPACT.search(combined):
        return IMPACT_MULTI_LANE

    if _EVENT_MEDIUM_IMPACT.search(combined):
        return IMPACT_SINGLE_LANE

    return IMPACT_LIGHT_PERMIT


def _special_event_status(record: dict) -> str:
    """Derive normalized status from special event dates."""
    today = date.today()
    start = _parse_date(record.get("start_date") or record.get("startdate"))
    end   = _parse_date(record.get("end_date") or record.get("enddate"))

    if end and end < today:
        return "completed"
    if start and start > today:
        return "planned"
    if start:
        return "active"
    return "unknown"


def normalize_special_event(record: dict) -> Project:
    """
    Normalize a raw Chicago special event permit record into a canonical Project.

    Args:
        record: A single dict from the chicago_special_events staging file.
                Fields: permit_id, event_name, start_date, end_date, event_type,
                        location, community_area, latitude, longitude.

    Returns:
        A Project dataclass ready for upsert into the `projects` table.
    """
    source_id  = str(record.get("permit_id") or record.get("id", ""))
    event_name = (record.get("event_name") or "").strip()
    event_type = (record.get("event_type") or "").strip()
    location   = (record.get("location") or "").strip() if isinstance(record.get("location"), str) else ""
    community  = (record.get("community_area") or "").strip()

    impact_type = _classify_special_event(event_type, event_name)

    # Title: event name (most descriptive).
    title = event_name or f"Special event {source_id}"
    if event_type and event_type.lower() not in title.lower():
        title = f"{event_type}: {title}"

    # Address: location field or community area + Chicago.
    addr_parts = []
    if location:
        addr_parts.append(location)
    elif community:
        addr_parts.append(community)
    addr_parts.append("Chicago, IL")
    address = ", ".join(addr_parts)

    notes = event_type[:200] if event_type else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    start = _parse_date(record.get("start_date") or record.get("startdate"))
    end   = _parse_date(record.get("end_date") or record.get("enddate"))

    return Project(
        project_id=f"chicago_event:{source_id}",
        source="chicago_special_events",
        source_id=source_id,
        impact_type=impact_type,
        title=title[:200],
        notes=notes,
        start_date=start,
        end_date=end,
        status=_special_event_status(record),
        address=address,
        latitude=lat,
        longitude=lon,
        severity_hint=IMPACT_SEVERITY[impact_type],
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _safe_float(value) -> Optional[float]:
    """Coerce a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Minimal smoke test — verifies classification logic without a DB.
    print("Running normalization smoke test...\n")

    test_permit = {
        "permit_": "TEST-001",
        "permit_type": "PERMIT - WRECKING/DEMOLITION",
        "work_description": "Demolish existing structure",
        "street_number": "1600",
        "street_direction": "W",
        "street_name": "Chicago Ave",
        "suffix": "",
        "issue_date": "2026-03-01T00:00:00",
        "expiration_date": "2026-09-01T00:00:00",
        "latitude": "41.8960",
        "longitude": "-87.6704",
    }

    p = normalize_permit(test_permit)
    print(f"Permit → impact_type: {p.impact_type} (expected: demolition)")
    print(f"         severity_hint: {p.severity_hint} (expected: HIGH)")
    print(f"         title: {p.title}")
    print(f"         project_id: {p.project_id}\n")

    test_closure = {
        "row_id": "CLOSE-999",
        "work_type": "Lane Closure",
        "street_closure_type": "Full Street Closure",
        "closure_reason": "Water main replacement",
        "street_name": "Grand Ave",
        "from_street": "N Halsted St",
        "to_street": "N Milwaukee Ave",
        "street_direction": "W",
        "start_date": "2026-03-18",
        "end_date": "2026-03-25",
        "status": "Approved",
        "latitude": "41.8908",
        "longitude": "-87.6476",
    }

    c = normalize_closure(test_closure)
    print(f"Closure → impact_type: {c.impact_type} (expected: closure_full)")
    print(f"          severity_hint: {c.severity_hint} (expected: HIGH)")
    print(f"          title: {c.title}")
    print(f"          status: {c.status}")
    print(f"          project_id: {c.project_id}\n")

    light_permit = {
        "permit_": "TEST-002",
        "permit_type": "PERMIT - SIGNS",
        "work_description": "Replace storefront sign",
        "street_number": "400",
        "street_direction": "N",
        "street_name": "Michigan Ave",
        "issue_date": "2026-03-10T00:00:00",
        "latitude": "41.8887",
        "longitude": "-87.6240",
    }

    lp = normalize_permit(light_permit)
    print(f"Light permit → impact_type: {lp.impact_type} (expected: light_permit)")
    print(f"              severity_hint: {lp.severity_hint} (expected: LOW)\n")

    test_idot = {
        "row_id": "42",
        "contract_number": "68B42",
        "construction_type": "Road Closed",
        "route": "S001",
        "location": "CRETE-RICHTON RD TO UNION AVE-RR",
        "near_town": "CRETE",
        "lanes_ramps_closed": "2",
        "start_date": "2026-02-26T12:00:00+00:00",
        "end_date": "2026-04-01T12:00:00+00:00",
        "latitude": 41.460073,
        "longitude": -87.634594,
    }

    idot = normalize_idot_project(test_idot)
    print(f"IDOT road → impact_type: {idot.impact_type} (expected: closure_full)")
    print(f"            severity_hint: {idot.severity_hint} (expected: HIGH)")
    print(f"            title: {idot.title}")
    print(f"            status: {idot.status}")
    print(f"            project_id: {idot.project_id}\n")

    print("Smoke test complete.")
