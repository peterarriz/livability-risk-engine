# Livability Risk Engine Demo Runbook

Use this for controlled founder-led demos. The product is nationwide in direction, with evidence depth varying by city and source coverage.

## Pre-demo checklist

- Confirm the latest frontend Vercel deployment is live.
- Confirm backend smoke checks pass in live mode.
- Confirm `/health` returns `status: ok`.
- Confirm `/score` works for at least one Chicago address and one non-Chicago address.
- Keep `ADMIN_SECRET`, API keys, Clerk keys, and Railway/Vercel dashboards off-screen.
- Have the backend smoke command ready as the fallback path.

## Backend smoke command

```bash
python3 scripts/demo_smoke_check.py \
  --backend-url "$BACKEND_URL" \
  --require-live \
  --address "1600 W Chicago Ave, Chicago, IL" \
  --address "350 5th Ave, New York, NY" \
  --address "600 Congress Ave, Austin, TX"
```

If `ADMIN_SECRET` is set, the script also checks protected DB readiness. It must never print the secret.

## Frontend pages to open

- `/` - public positioning and entry point
- `/app` - primary scoring workspace
- `/pilot-evidence` - pilot evidence and readiness summary
- `/api-access` - API access by request
- `/pricing` - pilot/design-partner positioning

## Approved demo addresses

- `1600 W Chicago Ave, Chicago, IL`
- `700 W Grand Ave, Chicago, IL`
- `5800 N Northwest Hwy, Chicago, IL`
- `350 5th Ave, New York, NY`
- `600 Congress Ave, Austin, TX`

## Coverage and evidence-quality talk track

- The score is live and nationwide-capable, but evidence depth varies by city and source.
- Chicago has the richest local construction/closure evidence today.
- Other cities may show lower evidence quality until more local sources are connected.
- Treat `evidence_quality`, `confidence`, `mode`, and `recommended_action` as part of the result, not footnotes.
- A low-evidence result is still useful because it tells the user how much to trust the score.

## Do not show yet

- Clerk admin screens or auth configuration.
- Billing, Stripe, paid-plan enforcement, quotas, or overage flows.
- Admin/debug endpoints such as `/debug/score`, `/health/db`, `/admin/stats`, or `/admin/watch/check`.
- Raw database tables, logs, secrets, API keys, or production infrastructure dashboards.
- Data-rich exports or internal operational endpoints unless explicitly requested and authorized.

## Known caveats

- Clerk is still test/dev for internal demo use.
- Self-serve billing is not live.
- API access is by request during the pilot stage.
- Usage is monitored during pilots; automated paid quota enforcement is not live.
- Evidence quality varies by city, source, and freshness.

## Emergency fallback

If the frontend has an issue, switch to backend output:

```bash
python3 scripts/demo_smoke_check.py --backend-url "$BACKEND_URL" --require-live
```

For a single address:

```bash
curl "$BACKEND_URL/score?address=1600%20W%20Chicago%20Ave%2C%20Chicago%2C%20IL"
```

Use the JSON response to show `livability_score`, `evidence_quality`, `confidence`, `recommended_action`, `top_risks`, and `mode`.
