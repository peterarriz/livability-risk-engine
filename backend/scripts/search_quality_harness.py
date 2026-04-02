"""Lightweight /suggest relevance harness for regression checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.routes.search import suggest_addresses


@dataclass
class Case:
    query: str
    expected_prefix: str = ""
    expected_canonical: str | None = None
    expected_min_results: int = 0
    expected_any_prefixes: tuple[str, ...] = ()
    note: str = ""


CASES = [
    # 20 real/realistic Chicago address queries (plus a few normalization forms).
    Case("233 s wacker", expected_prefix="233 S Wacker", expected_min_results=1, note="Willis Tower"),
    Case("875 n michigan", expected_prefix="875 N Michigan", expected_min_results=1, note="former Hancock"),
    Case("111 s michigan", expected_prefix="111 S Michigan", expected_min_results=1, note="Art Institute"),
    Case("201 e randolph", expected_prefix="201 E Randolph", expected_min_results=1, note="Millennium Park"),
    Case("400 s state", expected_prefix="400 S State", expected_min_results=1, note="Harold Washington Library"),
    Case("1060 w addison", expected_prefix="1060 W Addison", expected_min_results=1, note="Wrigley Field"),
    Case("1901 w madison", expected_prefix="1901 W Madison", expected_min_results=1, note="United Center"),
    Case("2301 s martin luther king", expected_prefix="2301 S Martin Luther King", expected_min_results=1, note="McCormick Place"),
    Case("1400 s dusable lake shore", expected_prefix="1400 S DuSable Lake Shore", expected_min_results=1, note="Museum Campus area"),
    Case("600 e grand", expected_prefix="600 E Grand", expected_min_results=1, note="Navy Pier"),
    Case("1200 w harrison", expected_prefix="1200 W Harrison", expected_min_results=1, note="UIC"),
    Case("225 n michigan", expected_prefix="225 N Michigan", expected_min_results=1, note="Aon/river corridor"),
    Case("1600 w chicago ave", expected_prefix="1600 W Chicago Ave", expected_min_results=1, note="Demo address"),
    Case("700 w grand", expected_prefix="700 W Grand Ave", expected_min_results=1, note="Demo address"),
    Case("900 w chicago", expected_prefix="900 W Chicago Ave", expected_min_results=1, note="Demo address"),
    # Edge normalization.
    Case("  1600   W.   CHICAGO ave  ", expected_prefix="1600 W Chicago Ave", expected_min_results=1, note="normalization"),
    Case("700-west-grand", expected_prefix="700 W Grand Ave", expected_min_results=1, note="delimiter robustness"),
    # Ambiguous queries should still provide candidates.
    Case("w chicago", expected_min_results=2, expected_any_prefixes=("1600 W Chicago Ave", "900 W Chicago Ave"), note="ambiguous corridor"),
    Case("chicago ave", expected_min_results=2, expected_any_prefixes=("1600 W Chicago Ave", "900 W Chicago Ave"), note="street-only ambiguity"),
    Case("michigan ave", expected_min_results=2, expected_any_prefixes=("875 N Michigan", "111 S Michigan", "225 N Michigan"), note="dense avenue ambiguity"),
]


def run() -> int:
    failures = 0
    failure_patterns: Counter[str] = Counter()
    labeled_results: list[tuple[str, str, str]] = []
    print("search-quality harness")
    for case in CASES:
        payload = suggest_addresses(case.query, limit=5)
        suggestions = payload.get("suggestions", [])
        top = suggestions[0] if suggestions else None

        passed = True
        failure_reason = ""
        if case.expected_prefix:
            if not top or not str(top.get("display_address", "")).startswith(case.expected_prefix):
                passed = False
                failure_reason = "wrong_top_match" if top else "no_results"
            if case.expected_canonical and (not top or top.get("canonical_id") != case.expected_canonical):
                passed = False
                failure_reason = "canonical_mismatch"
        if len(suggestions) < case.expected_min_results:
            passed = False
            failure_reason = "insufficient_results"
        if case.expected_any_prefixes:
            addresses = [str(item.get("display_address", "")) for item in suggestions]
            if not any(
                any(addr.startswith(prefix) for prefix in case.expected_any_prefixes)
                for addr in addresses
            ):
                passed = False
                failure_reason = "ambiguous_missing_candidate"
        if case.expected_min_results == 0 and not case.expected_prefix and not case.expected_any_prefixes and suggestions:
            passed = False
            failure_reason = "unexpected_noise"

        status = "correct" if passed else "incorrect"
        print(f"[{status.upper()}] query={case.query!r} count={len(suggestions)} top={top} note={case.note}")
        labeled_results.append((case.query, status, failure_reason))
        if not passed:
            failures += 1
            failure_patterns[failure_reason or "unknown"] += 1

    print(f"summary: {len(CASES) - failures}/{len(CASES)} passed")
    print("labels:")
    for query, status, reason in labeled_results:
        suffix = f" ({reason})" if reason else ""
        print(f"- {query!r}: {status}{suffix}")
    if failure_patterns:
        print("failure patterns:")
        for reason, count in failure_patterns.most_common():
            print(f"- {reason}: {count}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
