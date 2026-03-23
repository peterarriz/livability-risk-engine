#!/usr/bin/env python3
"""
scripts/validate_live.py
task: data-039
lane: data

End-to-end validation of the live Railway backend + Postgres DB.

Checks every condition from docs/deploy_readiness_checklist.md and exits
with a non-zero code if any check fails, so this can be used in CI or as
a manual operator sanity-check.

Usage:
    python scripts/validate_live.py --backend https://your-app.up.railway.app

Environment variable alternative:
    BACKEND_URL=https://your-app.up.railway.app python scripts/validate_live.py

Exit codes:
    0  — all checks passed
    1  — one or more checks failed
    2  — usage error (no backend URL provided)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

_failures: list[str] = []
_warnings: list[str] = []


def check(label: str, condition: bool, detail: str = "", warn_only: bool = False) -> bool:
    status = PASS if condition else (WARN if warn_only else FAIL)
    print(f"  [{status}] {label}")
    if detail:
        print(f"         {detail}")
    if not condition:
        if warn_only:
            _warnings.append(label)
        else:
            _failures.append(label)
    return condition


def get_json(url: str, timeout: int = 10) -> tuple[int, dict | None]:
    """Fetch JSON from URL. Returns (status_code, body_dict | None)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = None
        return e.code, body
    except Exception as exc:
        return 0, {"_error": str(exc)}


# ---------------------------------------------------------------------------
# Check groups
# ---------------------------------------------------------------------------

def check_health(backend: str) -> dict | None:
    print("\n1. /health endpoint")
    status, body = get_json(f"{backend}/health")

    ok = check("HTTP 200", status == 200, f"got status {status}")
    if not ok or not isinstance(body, dict):
        check("response body parseable", False, "cannot proceed with health checks")
        return None

    check("status == 'ok'", body.get("status") == "ok", f"got {body.get('status')!r}")
    check("db_configured == true", body.get("db_configured") is True, f"got {body.get('db_configured')!r}")
    check(
        "db_connection == true",
        body.get("db_connection") is True,
        f"got {body.get('db_connection')!r}",
    )
    check(
        "last_ingest_status reported",
        "last_ingest_status" in body,
        f"value={body.get('last_ingest_status')!r}",
        warn_only=True,
    )
    return body


def check_score(backend: str) -> dict | None:
    print("\n2. /score endpoint — live mode")
    addr = urllib.parse.quote("1600 W Chicago Ave, Chicago, IL")
    status, body = get_json(f"{backend}/score?address={addr}")

    ok = check("HTTP 200", status == 200, f"got status {status}")
    if not ok or not isinstance(body, dict):
        check("response body parseable", False, "cannot proceed with score checks")
        return None

    check("mode == 'live'", body.get("mode") == "live", f"got {body.get('mode')!r}")
    check("fallback_reason is null", body.get("fallback_reason") is None, f"got {body.get('fallback_reason')!r}")
    check(
        "disruption_score is a number",
        isinstance(body.get("disruption_score"), (int, float)),
        f"got {body.get('disruption_score')!r}",
    )
    check(
        "confidence is valid",
        body.get("confidence") in ("LOW", "MEDIUM", "HIGH"),
        f"got {body.get('confidence')!r}",
    )
    check(
        "top_risks is non-empty list",
        isinstance(body.get("top_risks"), list) and len(body.get("top_risks", [])) > 0,
        f"got {body.get('top_risks')!r}",
        warn_only=True,
    )
    check(
        "top_risk_details present",
        isinstance(body.get("top_risk_details"), list),
        f"got {type(body.get('top_risk_details')).__name__}",
        warn_only=True,
    )
    check(
        "latitude returned",
        body.get("latitude") is not None,
        f"got {body.get('latitude')!r}",
        warn_only=True,
    )
    return body


def check_debug_score(backend: str) -> None:
    print("\n3. /debug/score endpoint — project count")
    addr = urllib.parse.quote("1600 W Chicago Ave, Chicago, IL")
    status, body = get_json(f"{backend}/debug/score?address={addr}")

    ok = check("HTTP 200", status == 200, f"got status {status}")
    if not ok or not isinstance(body, dict):
        check("response body parseable", False, "cannot proceed with debug checks")
        return

    check("mode == 'live'", body.get("mode") == "live", f"got {body.get('mode')!r}")
    count = body.get("nearby_projects_count", -1)
    check(
        "nearby_projects_count > 0",
        isinstance(count, int) and count > 0,
        f"got {count} — if 0, ingest may not have run or radius too small",
    )


def check_second_address(backend: str) -> None:
    print("\n4. /score endpoint — second address (sanity)")
    addr = urllib.parse.quote("233 S Wacker Dr, Chicago, IL")
    status, body = get_json(f"{backend}/score?address={addr}")

    ok = check("HTTP 200", status == 200, f"got status {status}")
    if not ok or not isinstance(body, dict):
        return

    check("mode == 'live'", body.get("mode") == "live", f"got {body.get('mode')!r}")
    check(
        "disruption_score returned",
        isinstance(body.get("disruption_score"), (int, float)),
        f"got {body.get('disruption_score')!r}",
    )


def check_history(backend: str) -> None:
    print("\n5. /history endpoint")
    addr = urllib.parse.quote("1600 W Chicago Ave, Chicago, IL")
    status, body = get_json(f"{backend}/history?address={addr}&limit=5")

    ok = check("HTTP 200", status == 200, f"got status {status}")
    if not ok or not isinstance(body, dict):
        return

    check(
        "history array present",
        isinstance(body.get("history"), list),
        f"got {type(body.get('history')).__name__}",
    )
    history = body.get("history", [])
    check(
        "at least one history entry",
        len(history) > 0,
        f"got {len(history)} rows — submit a /score request first if empty",
        warn_only=True,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate live Railway backend end-to-end.")
    parser.add_argument(
        "--backend",
        default=os.environ.get("BACKEND_URL", ""),
        help="Railway backend base URL (e.g. https://your-app.up.railway.app)",
    )
    args = parser.parse_args()

    if not args.backend:
        print("ERROR: provide --backend <url> or set BACKEND_URL env var", file=sys.stderr)
        return 2

    backend = args.backend.rstrip("/")
    print(f"Validating: {backend}")
    print("=" * 60)

    health = check_health(backend)
    score = check_score(backend)
    check_debug_score(backend)
    check_second_address(backend)
    check_history(backend)

    print("\n" + "=" * 60)
    if _failures:
        print(f"\033[31mFAILED\033[0m — {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"  • {f}")
        if _warnings:
            print(f"\n{len(_warnings)} warning(s):")
            for w in _warnings:
                print(f"  • {w}")
        return 1

    if _warnings:
        print(f"\033[32mPASSED\033[0m with {len(_warnings)} warning(s):")
        for w in _warnings:
            print(f"  • {w}")
    else:
        print("\033[32mAll checks passed. Deploy is live-ready.\033[0m")

    if score:
        print(f"\nScore sample (1600 W Chicago Ave): {score.get('disruption_score')} / 100"
              f"  confidence={score.get('confidence')}  mode={score.get('mode')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
