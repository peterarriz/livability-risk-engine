# Design-Partner Pilot Terms

Use this document when agreeing on pilot terms with a design-partner candidate. These terms are intentionally simple — they should be confirmable via email without a formal contract. The goal is to lower friction to a yes while being clear about mutual commitments.

---

## What we offer (our commitment)

1. **Free API access for 30 days** from the date of first API key delivery, at up to 500 address lookups included.
2. **Dedicated onboarding**: a 30-minute setup call and written instructions for integrating the `/score` endpoint into the partner's workflow.
3. **Direct feedback channel**: a shared Slack channel or email thread where the partner can flag issues or questions during the pilot.
4. **Honest response to every issue**: we will acknowledge every accuracy complaint within 24 hours and provide a root-cause explanation within 5 business days.
5. **No commitment beyond the pilot**: at the end of 30 days, the partner has no obligation to convert to a paid tier. If they do, they receive 20% off their first paid month as a design-partner discount.

---

## What we ask (partner commitment)

1. **Run the API on at least 20 real addresses** from their actual workflow (deals, dispatch routes, or listings) during the 30-day pilot.
2. **Complete one 30-minute feedback session** at the midpoint (day 14–18) covering: which outputs were most useful, which were confusing or wrong, and what is missing.
3. **Share one written summary** at the end of the pilot (a short email or Loom is fine) covering: overall signal quality, most useful outputs, and biggest gaps.
4. **Provide at least one specific example** of an address where the score was surprising or incorrect (with the address and their expected result), so we can investigate and improve.
5. **Permission to reference the firm name** in future pitches as a design partner (without quoting specific deal details), unless they opt out.

---

## Scope boundaries (what this pilot is not)

- This is not a production deployment. The API is MVP-stage and will have gaps in data coverage and occasional inconsistencies in score calibration.
- The score is based on Chicago public permit and closure data. It does not include utility outages, CTA disruptions, or real-time traffic. We will state this clearly.
- The pilot does not include any custom data integrations, white-label output, or dedicated SLA guarantees.
- This is not a legal contract. It is a mutual understanding documented via email confirmation.

---

## Pilot timeline

| Day | Milestone |
| --- | --- |
| 0 | Pilot confirmed via email; API key delivered |
| 1–3 | Onboarding call; partner runs first address lookups |
| 14–18 | Midpoint feedback session (30 minutes) |
| 25–28 | Partner submits written summary |
| 30 | Pilot ends; partner decides whether to convert to paid |
| 30+ | If converting, design-partner discount applied to first paid month |

---

## Conversion offer at pilot end

| Tier | Standard price | Design-partner first-month price |
| --- | --- | --- |
| Spot | $0.10/call | Free first 100 calls, then $0.08/call for 90 days |
| Professional | $299/month | $239/month for first 3 months |
| Enterprise | $1,500+/month | Custom — discuss based on pilot volume and feedback |

---

## Sample confirmation email (send to partner after verbal agreement)

> Hi [First Name],
>
> Great — here's a quick summary of what we agreed on for the pilot:
>
> **What we're providing**: free API access for 30 days (up to 500 address lookups), a 30-minute setup call, and a direct support channel for the duration.
>
> **What we're asking from you**: run the API on at least 20 real addresses from your workflow, join a 30-minute check-in around day 15, and share a short summary at the end of the 30 days.
>
> I'll send the API key and setup instructions within 24 hours. Looking forward to getting started.
>
> [Your name]

Reply with "Confirmed" or any questions and we'll consider the pilot officially underway.

---

## Tracking pilots

Maintain a simple log for each active pilot:

| Partner | Persona | Start date | API calls used | Midpoint session | End summary | Converted? |
| --- | --- | --- | --- | --- | --- | --- |
| [Firm] | CRE | [date] | [count] | [✓/pending] | [✓/pending] | [Yes/No/TBD] |
