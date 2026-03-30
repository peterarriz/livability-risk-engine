"""
backend/app/routes/watchlist.py

Score alert watchlist endpoints — extracted from main.py.

Endpoints:
  POST /watch and POST /watchlist — subscribe to alerts
  GET  /watchlist                 — list user's watched addresses
  GET  /watch/unsubscribe         — unsubscribe via token
  POST /admin/watch/check         — admin trigger to check thresholds
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.app.deps import _is_db_configured

log = logging.getLogger(__name__)

router = APIRouter()


class WatchRequest(BaseModel):
    email: str | None = None
    address: str
    threshold: int  # 0–100 disruption score


@router.post("/watch")
@router.post("/watchlist")
def subscribe_watch(body: WatchRequest, authorization: str = Header(default=None)) -> dict:
    """Subscribe an email address to score alerts for an address."""
    if not (0 <= body.threshold <= 100):
        raise HTTPException(status_code=422, detail="threshold must be between 0 and 100.")

    from backend.app.auth import get_current_user_optional
    user = get_current_user_optional(authorization)
    account_id = int(user["sub"]) if user and user.get("sub") else None
    email = (body.email or (user.get("email") if user else None) or "").strip()

    if not _is_db_configured():
        log.info(
            "watch subscribe (demo) email=%r address=%r threshold=%d",
            email, body.address, body.threshold,
        )
        return {
            "id": None,
            "email": email,
            "address": body.address,
            "threshold": body.threshold,
            "token": None,
            "demo": True,
            "message": "Noted. Alert delivery activates once the live database is connected.",
        }

    try:
        from backend.scoring.query import get_db_connection

        token = secrets.token_hex(32)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlist (email, address, threshold_score, token, account_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (email, address)
                    DO UPDATE SET
                        threshold_score = EXCLUDED.threshold_score,
                        token = EXCLUDED.token,
                        account_id = COALESCE(EXCLUDED.account_id, watchlist.account_id)
                    RETURNING id, token
                    """,
                    (email, body.address, body.threshold, token, account_id),
                )
                row = cur.fetchone()
                watch_id, stored_token = row[0], row[1]
            conn.commit()
        finally:
            conn.close()

        log.info(
            "watch subscribe id=%d email=%r address=%r threshold=%d",
            watch_id, email, body.address, body.threshold,
        )
        return {
            "id": watch_id,
            "email": email,
            "address": body.address,
            "threshold": body.threshold,
            "token": stored_token,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("subscribe_watch error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not create watchlist entry.") from exc


@router.get("/watchlist")
def get_watchlist(authorization: str = Header(default=None)) -> dict:
    """Return active watchlist entries for the authenticated user."""
    from backend.app.auth import get_current_user
    user = get_current_user(authorization)
    account_id = int(user["sub"])

    if not _is_db_configured():
        return {"entries": []}

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, address, threshold_score, created_at, is_active
                    FROM watchlist
                    WHERE account_id = %s AND is_active = true
                    ORDER BY created_at DESC
                    """,
                    (account_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        return {
            "entries": [
                {
                    "id": r[0],
                    "email": r[1],
                    "address": r[2],
                    "threshold": r[3],
                    "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                    "is_active": r[5],
                }
                for r in rows
            ]
        }
    except Exception as exc:
        log.error("get_watchlist error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not fetch watchlist.") from exc


@router.get("/watch/unsubscribe")
def unsubscribe_watch(token: str = Query(..., description="Unsubscribe token from watchlist entry")) -> dict:
    """Remove a watchlist subscription by its unsubscribe token."""
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Watchlist requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlist WHERE token = %s RETURNING id, email, address",
                    (token,),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Watchlist entry not found.")

        watch_id, email, address = row
        log.info("watch unsubscribe id=%d email=%r address=%r", watch_id, email, address)
        return {"unsubscribed": True, "id": watch_id, "email": email, "address": address}

    except HTTPException:
        raise
    except Exception as exc:
        log.error("unsubscribe_watch error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not process unsubscribe.") from exc


@router.post("/admin/watch/check")
def check_watchlist() -> dict:
    """
    Operator endpoint — score every watched address and fire alerts.
    Intended to be called on a schedule (e.g. daily cron).
    """
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Watchlist requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, address, threshold_score FROM watchlist")
                entries = cur.fetchall()
        finally:
            conn.close()

        alerts_fired = []

        for watch_id, email, address, threshold in entries:
            try:
                # Import _score_live from extracted score module
                from backend.app.routes.score import _score_live
                result = _score_live(address)
                score = result.get("disruption_score")
                if score is None:
                    continue

                if score >= threshold:
                    log.info(
                        "ALERT [stub] watch_id=%d email=%r address=%r "
                        "score=%d threshold=%d — would send alert email",
                        watch_id, email, address, score, threshold,
                    )

                    conn2 = get_db_connection()
                    try:
                        with conn2.cursor() as cur2:
                            cur2.execute(
                                "INSERT INTO alert_log (watchlist_id, disruption_score) VALUES (%s, %s)",
                                (watch_id, score),
                            )
                        conn2.commit()
                    finally:
                        conn2.close()

                    alerts_fired.append({
                        "watch_id": watch_id,
                        "email": email,
                        "address": address,
                        "score": score,
                        "threshold": threshold,
                    })
            except Exception as exc:
                log.warning("check_watchlist entry id=%d error: %s", watch_id, exc)
                continue

        log.info("check_watchlist complete entries=%d alerts_fired=%d", len(entries), len(alerts_fired))
        return {
            "entries_checked": len(entries),
            "alerts_fired": len(alerts_fired),
            "alerts": alerts_fired,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("check_watchlist error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not check watchlist.") from exc
