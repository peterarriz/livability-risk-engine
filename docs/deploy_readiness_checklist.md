# Deploy Readiness Checklist

Use this checklist to quickly determine whether the app is truly running in live mode or still falling back to the approved demo scenario.

## Core readiness checks

### 1. Confirm `NEXT_PUBLIC_API_URL` is configured
- Verify the deployed frontend has `NEXT_PUBLIC_API_URL` set to the intended backend base URL.
- If this value is missing, the frontend will fabricate the demo response and the app will not be using the live backend.

### 2. Confirm backend `/health` is reachable
Run:

```bash
curl -s http://<backend-host>/health | python3 -m json.tool
```

Check that:
- the endpoint responds successfully
- `status` is `"ok"`
- `mode` is `"live"` for a live deployment
- `db_configured` is `true`
- `db_connection` is `true`

If `/health` is not reachable, stop here and treat the deploy as not ready.

### 3. Confirm `/score` returns `mode` correctly
Run:

```bash
curl -s "http://<backend-host>/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" | python3 -m json.tool
```

Check that:
- `mode` is `"live"` for a real live deployment
- `fallback_reason` is `null` in live mode
- if `mode` is `"demo"`, the deploy is still falling back and should not be treated as fully live

### 4. Confirm `/debug/score` returns nearby projects for a high-activity address
Run:

```bash
curl -s "http://<backend-host>/debug/score?address=1600%20W%20Chicago%20Ave,%20Chicago,%20IL" | python3 -m json.tool
```

Check that:
- `mode` is `"live"`
- `fallback_reason` is `null`
- `nearby_projects_count` is greater than `0`
- `nearby_projects_sample` includes real nearby project records

If `nearby_projects_count` is `0` for this address, confirm the ingest/load path before calling the deploy live-ready.

### 5. Confirm the frontend clearly shows Live data or Demo scenario
Open the deployed frontend and submit `1600 W Chicago Ave, Chicago, IL`.

Check that:
- the results view shows **"Live data • Chicago"** when the backend response is live
- the results view shows **"Demo scenario"** when the backend or frontend is falling back
- the label is visible without opening DevTools

## Common failure modes

### Missing API URL
**Symptom:** the frontend always shows the demo scenario regardless of backend state.

**Likely cause:** `NEXT_PUBLIC_API_URL` is missing or incorrect.

**Fix:** set the deployed frontend environment variable to the correct backend URL and redeploy.

### Unreachable backend
**Symptom:** the frontend falls back to demo mode and `/health` cannot be reached.

**Likely cause:** backend service is down, misrouted, or blocked by networking.

**Fix:** verify backend process, routing, DNS, and firewall/load-balancer configuration.

### Geocoding failure
**Symptom:** `/score` returns `mode: "demo"` with `fallback_reason: "geocode_failed"`.

**Likely cause:** the live path is running, but address geocoding failed for the submitted query.

**Fix:** inspect `/debug/score`, verify geocoder reachability, and confirm the address format is valid Chicago input.

### DB/config issue
**Symptom:** `/health` shows `db_configured: true` but `db_connection: false`, or `/score` returns a backend failure instead of a live result.

**Likely cause:** incorrect DB credentials, unreachable DB host, or the canonical projects table is not available.

**Fix:** verify `POSTGRES_*` configuration, DB connectivity, and the live data load path before retrying the deploy check.

## Ready / not ready decision

Mark the deploy **ready** only when all of the following are true:
- `NEXT_PUBLIC_API_URL` is configured correctly
- backend `/health` is reachable and shows live DB connectivity
- `/score` returns `mode: "live"`
- `/debug/score` returns nearby projects for `1600 W Chicago Ave, Chicago, IL`
- the frontend visibly shows **"Live data • Chicago"**

If any one of these checks fails, treat the deploy as **not ready** for live-score use and investigate the fallback path first.
