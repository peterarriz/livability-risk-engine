#!/usr/bin/env python3
"""
Non-destructive demo-readiness smoke check for a running LRE backend.

The script calls only HTTP endpoints on the configured backend URL. It never
connects directly to the database, runs ingestion, or prints supplied secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_ADDRESSES = [
    "1600 W Chicago Ave, Chicago, IL",
    "700 W Grand Ave, Chicago, IL",
    "111 N Halsted St, Chicago, IL",
    "5800 N Northwest Hwy, Chicago, IL",
    "11900 S Morgan St, Chicago, IL",
]

HEALTH_DB_DISPLAY_FIELDS = (
    "status",
    "db_configured",
    "last_ingest_status",
    "last_ingest_count",
    "last_ingest_at",
)


@dataclass
class JsonResponse:
    status: int
    body: Any
    error: str | None = None


def _status(label: str, message: str) -> None:
    print(f"[{label}] {message}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _in_score_range(value: Any) -> bool:
    return _is_number(value) and 0 <= value <= 100


def _display_url(url: str) -> str:
    """Return a URL safe for terminal output by dropping userinfo/query/fragment."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path.rstrip("/"), "", ""))


def _normalize_backend_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme:
        url = f"http://{url}"
        parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("backend URL must be an http(s) URL")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _get_json(url: str, headers: dict[str, str], timeout: float) -> JsonResponse:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return JsonResponse(resp.status, json.loads(raw) if raw else None)
            except json.JSONDecodeError:
                return JsonResponse(resp.status, None, "response was not valid JSON")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        body: Any = None
        if raw:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"detail": raw[:200]}
        return JsonResponse(exc.code, body, f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return JsonResponse(0, None, f"request failed: {reason}")


def _body_detail(body: Any) -> str:
    if isinstance(body, dict):
        detail = body.get("detail")
        if detail:
            return str(detail)[:200]
    return ""


def check_health(backend_url: str, timeout: float, require_live: bool) -> int:
    resp = _get_json(f"{backend_url}/health", headers={}, timeout=timeout)
    if resp.status != 200:
        detail = _body_detail(resp.body)
        suffix = f" - {detail}" if detail else ""
        _status("FAIL", f"/health: {resp.error or 'unexpected response'}{suffix}")
        return 1
    if not isinstance(resp.body, dict):
        _status("FAIL", "/health: response was not a JSON object")
        return 1

    status = resp.body.get("status")
    mode = resp.body.get("mode")
    db_configured = resp.body.get("db_configured")
    if status != "ok":
        _status("FAIL", f"/health: status={status!r}")
        return 1
    if require_live and mode != "live":
        _status("FAIL", f"/health: mode={mode!r}, expected 'live'")
        return 1

    _status("PASS", f"/health: status={status} mode={mode} db_configured={db_configured}")
    return 0


def check_health_db(
    backend_url: str,
    admin_secret: str | None,
    timeout: float,
    require_live: bool,
) -> int:
    if not admin_secret:
        _status("SKIP", "/health/db: ADMIN_SECRET not provided")
        return 0

    headers = {"X-Admin-Secret": admin_secret}
    resp = _get_json(f"{backend_url}/health/db", headers=headers, timeout=timeout)
    if resp.status != 200:
        detail = _body_detail(resp.body)
        suffix = f" - {detail}" if detail else ""
        _status("FAIL", f"/health/db: {resp.error or 'unexpected response'}{suffix}")
        return 1
    if not isinstance(resp.body, dict):
        _status("FAIL", "/health/db: response was not a JSON object")
        return 1
    if resp.body.get("status") != "ok":
        _status("FAIL", f"/health/db: status={resp.body.get('status')!r}")
        return 1
    if require_live and resp.body.get("db_configured") is not True:
        _status("FAIL", "/health/db: db_configured is not true")
        return 1
    if require_live and resp.body.get("db_connection") is False:
        _status("FAIL", "/health/db: db_connection is false")
        return 1

    fields = [
        f"{field}={resp.body.get(field)!r}"
        for field in HEALTH_DB_DISPLAY_FIELDS
        if field in resp.body
    ]
    _status("PASS", f"/health/db: {' '.join(fields)}")
    return 0


def _validate_score_body(body: Any, require_live: bool) -> list[str]:
    failures: list[str] = []
    if not isinstance(body, dict):
        return ["response was not a JSON object"]

    if body.get("error"):
        failures.append(f"top-level error={body.get('error')!r}")

    if not _in_score_range(body.get("livability_score")):
        failures.append("livability_score missing or outside 0..100")

    if "disruption_score" in body and body.get("disruption_score") is not None:
        if not _in_score_range(body.get("disruption_score")):
            failures.append("disruption_score outside 0..100")

    if body.get("confidence") in (None, ""):
        failures.append("confidence missing")
    if body.get("evidence_quality") in (None, ""):
        failures.append("evidence_quality missing")

    action = body.get("recommended_action")
    if not isinstance(action, str) or not action.strip():
        failures.append("recommended_action missing or empty")

    severity = body.get("severity")
    if not isinstance(severity, dict):
        failures.append("severity missing or not an object")
    else:
        for field in ("noise", "traffic", "dust"):
            if severity.get(field) in (None, ""):
                failures.append(f"severity.{field} missing")

    if not isinstance(body.get("top_risks"), list):
        failures.append("top_risks missing or not a list")

    explanation = body.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        failures.append("explanation missing or empty")

    mode = body.get("mode")
    if mode in (None, ""):
        failures.append("mode missing")
    elif require_live and mode != "live":
        failures.append(f"mode={mode!r}, expected 'live'")

    fallback_reason = body.get("fallback_reason")
    if mode == "live" and fallback_reason not in (None, ""):
        failures.append(f"fallback_reason={fallback_reason!r} for live response")

    return failures


def check_score(
    backend_url: str,
    address: str,
    api_key: str | None,
    timeout: float,
    require_live: bool,
) -> int:
    query = urllib.parse.urlencode({"address": address})
    headers = {"X-API-Key": api_key} if api_key else {}
    resp = _get_json(f"{backend_url}/score?{query}", headers=headers, timeout=timeout)

    if resp.status != 200:
        detail = _body_detail(resp.body)
        suffix = f" - {detail}" if detail else ""
        _status("FAIL", f"/score {address!r}: {resp.error or 'unexpected response'}{suffix}")
        return 1

    failures = _validate_score_body(resp.body, require_live=require_live)
    if failures:
        _status("FAIL", f"/score {address!r}: {'; '.join(failures)}")
        return 1

    body = resp.body
    _status(
        "PASS",
        (
            f"/score {address!r}: "
            f"livability_score={body.get('livability_score')} "
            f"confidence={body.get('confidence')} "
            f"evidence_quality={body.get('evidence_quality')} "
            f"mode={body.get('mode')} "
            f"recommended_action={body.get('recommended_action')!r}"
        ),
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a non-destructive demo-readiness smoke check against an LRE backend."
    )
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", ""),
        help="Backend base URL. Defaults to BACKEND_URL.",
    )
    parser.add_argument(
        "--address",
        action="append",
        default=[],
        help="Address to check. Repeat for multiple addresses. Defaults to the documented smoke set.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LRE_API_KEY", ""),
        help="Optional API key for X-API-Key. Defaults to LRE_API_KEY.",
    )
    parser.add_argument(
        "--admin-secret",
        default=os.environ.get("ADMIN_SECRET", ""),
        help="Optional admin secret for /health/db. Defaults to ADMIN_SECRET.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds for each request. Default: 15.",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Fail if /health or any /score response is not in live mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        print("ERROR: --timeout must be greater than 0", file=sys.stderr)
        return 2
    if not args.backend_url:
        print("ERROR: provide --backend-url or set BACKEND_URL", file=sys.stderr)
        return 2

    try:
        backend_url = _normalize_backend_url(args.backend_url)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    addresses = args.address or DEFAULT_ADDRESSES
    api_key = args.api_key.strip() or None
    admin_secret = args.admin_secret.strip() or None

    print("Demo readiness smoke check")
    print(f"Backend: {_display_url(backend_url)}")
    print(f"Addresses: {len(addresses)}")
    print(f"API key: {'provided' if api_key else 'not provided'}")
    print(f"Admin secret: {'provided' if admin_secret else 'not provided'}")
    print(f"Require live: {args.require_live}")
    print()

    failures = 0
    failures += check_health(backend_url, args.timeout, args.require_live)
    failures += check_health_db(backend_url, admin_secret, args.timeout, args.require_live)

    for address in addresses:
        failures += check_score(backend_url, address, api_key, args.timeout, args.require_live)

    print()
    if failures:
        _status("FAIL", f"demo smoke check failed with {failures} required check failure(s)")
        return 1

    _status("PASS", "demo smoke check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
