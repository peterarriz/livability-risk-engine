"""Shared address normalization helpers for search and scoring paths."""
from __future__ import annotations

import re

STREET_SUFFIX_NORMALIZATION = {
    "st": "street",
    "street": "street",
    "ave": "avenue",
    "av": "avenue",
    "avenue": "avenue",
    "blvd": "boulevard",
    "boulevard": "boulevard",
    "dr": "drive",
    "drive": "drive",
    "rd": "road",
    "road": "road",
    "ln": "lane",
    "lane": "lane",
    "ct": "court",
    "court": "court",
    "pl": "place",
    "place": "place",
    "pkwy": "parkway",
    "parkway": "parkway",
    "ter": "terrace",
    "terrace": "terrace",
}

DIRECTION_NORMALIZATION = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}


def normalize_address_query(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = s.replace(".", " ").replace(",", " ")
    s = re.sub(r"[^\w\s#-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    tokens: list[str] = []
    for token in s.split():
        token = DIRECTION_NORMALIZATION.get(token, token)
        token = STREET_SUFFIX_NORMALIZATION.get(token, token)
        tokens.append(token)
    return " ".join(tokens)


def build_address_search_tokens(raw: str) -> list[str]:
    return [tok for tok in normalize_address_query(raw).split() if len(tok) >= 2]


def normalize_address_record(display_address: str) -> dict[str, str]:
    normalized = normalize_address_query(display_address)
    parts = [p.strip() for p in (display_address or "").split(",") if p.strip()]
    street = normalize_address_query(parts[0] if parts else display_address)
    city = normalize_address_query(parts[1] if len(parts) >= 2 else "")
    state_zip = parts[2] if len(parts) >= 3 else ""
    state_match = re.search(r"\b([A-Za-z]{2})\b", state_zip)
    state = state_match.group(1).upper() if state_match else ""
    return {
        "normalized_full": normalized,
        "street": street,
        "city": city,
        "state": state,
    }


def format_display_address(street: str, city: str, state: str, zip_code: str | None = None) -> str:
    locality = ", ".join(part for part in [city, state] if part)
    base = f"{street}, {locality}".strip().strip(",")
    if zip_code:
        return f"{base} {zip_code}".strip()
    return base
