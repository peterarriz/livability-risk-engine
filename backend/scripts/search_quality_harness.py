"""Lightweight /suggest relevance harness for regression checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import suggest_addresses


@dataclass
class Case:
    query: str
    expected_prefix: str
    expected_canonical: str | None = None


CASES = [
    Case("1600 w chicago ave", "1600 W Chicago Ave", "addr_demo_1"),
    Case("700 w grand", "700 W Grand Ave", "addr_demo_2"),
    Case("233 s wacker", "233 S Wacker Dr", "addr_demo_3"),
    Case("44th", "", None),  # should avoid weak token-only noise
]


def run() -> int:
    failures = 0
    print("search-quality harness")
    for case in CASES:
        payload = suggest_addresses(case.query, limit=5)
        suggestions = payload.get("suggestions", [])
        top = suggestions[0] if suggestions else None

        passed = True
        if case.expected_prefix:
            if not top or not str(top.get("display_address", "")).startswith(case.expected_prefix):
                passed = False
            if case.expected_canonical and (not top or top.get("canonical_id") != case.expected_canonical):
                passed = False
        else:
            if suggestions:
                passed = False

        status = "PASS" if passed else "FAIL"
        print(f"[{status}] query={case.query!r} top={top}")
        if not passed:
            failures += 1

    print(f"summary: {len(CASES) - failures}/{len(CASES)} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
