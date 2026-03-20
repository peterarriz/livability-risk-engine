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

# Base weights per docs/03_scoring_model.md
BASE_WEIGHTS: dict[str, int] = {
    IMPACT_FULL_CLOSURE:  45,
    IMPACT_MULTI_LANE:    38,
    IMPACT_SINGLE_LANE:   28,
    IMPACT_DEMOLITION:    24,
    IMPACT_CONSTRUCTION:      16,
    IMPACT_ROAD_CONSTRUCTION: 20,
    IMPACT_LIGHT_PERMIT:       8,
}

# Severity hints derived from impact type for normalization pre-computation.
IMPACT_SEVERITY: dict[str, str] = {
    IMPACT_FULL_CLOSURE:  "HIGH",
    IMPACT_MULTI_LANE:    "HIGH",
    IMPACT_SINGLE_LANE:   "MEDIUM",
    IMPACT_DEMOLITION:    "HIGH",
    IMPACT_CONSTRUCTION:      "MEDIUM",
    IMPACT_ROAD_CONSTRUCTION: "MEDIUM",
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

    work_type = record.get("work_type", "").strip()
    if work_type:
        parts.append(f"({work_type})")

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
    source_id = (
        record.get("project_number")
        or record.get("source_id")
        or ""
    )
    work_type = record.get("work_type", "")
    description = record.get("project_description", "")

    impact_type = _classify_idot_project(work_type, description)

    # Title: route + work type for quick scanning.
    route = (record.get("route") or "").strip()
    county = (record.get("county") or "").strip()
    title_parts = []
    if route:
        title_parts.append(route)
    if county:
        title_parts.append(f"({county} Co.)")
    if work_type:
        title_parts.append(f"— {work_type}")
    title = " ".join(title_parts) if title_parts else f"IDOT project {source_id}"

    notes = description[:200] if description else None

    lat = _safe_float(record.get("latitude"))
    lon = _safe_float(record.get("longitude"))

    # Fallback: extract from nested location dict.
    if (lat is None or lon is None) and isinstance(record.get("location"), dict):
        loc = record["location"]
        lat = _safe_float(loc.get("latitude"))
        lon = _safe_float(loc.get("longitude"))

    address_str = _idot_address(record)

    return Project(
        project_id=f"idot_road_projects:{source_id}",
        source="idot_road_projects",
        source_id=source_id,
        impact_type=impact_type,
        title=title,
        notes=notes,
        start_date=_parse_date(record.get("start_date") or record.get("contract_date")),
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

    idot = normalize_idot_road_project(test_idot)
    print(f"IDOT road → impact_type: {idot.impact_type} (expected: closure_full)")
    print(f"            severity_hint: {idot.severity_hint} (expected: HIGH)")
    print(f"            title: {idot.title}")
    print(f"            status: {idot.status}")
    print(f"            project_id: {idot.project_id}\n")

    print("Smoke test complete.")
