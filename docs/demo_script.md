# Demo Script — Investor and Stakeholder Walkthrough

This script is for anyone demoing the Livability Risk Engine to an investor, design-partner prospect, or stakeholder. It covers the full address-to-score flow using the approved demo responses from `docs/04_api_contracts.md`.

**Total demo time**: 8–12 minutes for a full walkthrough. 3–5 minutes for a focused API-only pitch.

**Setup before the demo**:
- Have the frontend running locally or open the deployed demo URL.
- Have `docs/04_api_contracts.md` open in a separate tab for reference.
- Know your audience's persona: CRE analyst, logistics operator, or proptech builder. Adjust talking points below accordingly.

---

## Part 1 — The problem (2 minutes)

**Say**: "Before I show you the product, I want to set up the problem it solves."

"Imagine you are about to close on a commercial property at 1600 W Chicago Ave in West Town. It is a $2 million deal. You have done your market comp analysis, your cap rate math, your tenant review. But no one on your team has checked whether there is a major street closure starting on that block next week. That information exists — it is sitting in a public city database — but it takes an analyst 30 to 60 minutes to find it, interpret it, and turn it into a usable signal."

"We built a single API call that does that in under half a second."

*[For logistics audience]* "Or imagine you are routing 200 deliveries a day. One of your most frequent drop-off zones has had a lane closure for two weeks. Your drivers keep calling in delays. That closure was in the city permit system the day it was issued — but no one in your dispatch workflow had a fast way to see it."

---

## Part 2 — The API (3–4 minutes)

**Say**: "Let me show you the actual product."

**Step 1 — Input an address**

Type or paste into the frontend: `1600 W Chicago Ave, Chicago, IL`

*Talking point*: "This is a real West Town address on a major arterial. We chose it for demos because it has typical Chicago permit and closure activity — nothing extreme, but enough to show a meaningful signal."

**Step 2 — Show the score**

The response returns `disruption_score: 62`, `confidence: MEDIUM`, and severity fields.

*Talking point*: "The score is 62 out of 100. That puts us in the High band — material disruption expected in the near term, but not Severe. The confidence is Medium because we have specific timing data but the location match is at street level, not GPS-precise."

*[For CRE audience]*: "This is the number you would put in a deal memo. It tells you this address has elevated near-term disruption risk and warrants a closer look before closing."

*[For logistics audience]*: "This is the threshold number for your dispatch system. A score above 50 means pre-plan an alternate curb access window or notify the driver before dispatch."

**Step 3 — Show the top risks**

Point to the three `top_risks` bullets:
1. "2-lane eastbound closure on W Chicago Ave within roughly 120 meters"
2. "Active closure window runs through 2026-03-22"
3. "Traffic and curb access are the dominant near-term disruption signals at this address"

*Talking point*: "These are plain-English, display-ready strings. No reformatting needed. A CRE analyst pastes these into a deal memo. A proptech platform renders them as bullet points under a listing. A dispatch manager forwards them to a driver."

**Step 4 — Show the explanation**

Point to the `explanation` field: "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic and curb access disruption even though noise and dust are limited."

*Talking point*: "This is one paragraph, deterministic, and calibrated to the score band. If the score is Low, the explanation tone is calm. If it is Severe, it is strongly cautionary. The tone never oversells or undersells what the data actually supports."

---

## Part 3 — The full range (2 minutes)

**Say**: "Let me show you the full range so you can see how the model behaves across different scenarios."

Walk through all four approved examples from `docs/04_api_contracts.md`:

| Address | Score | Band | Key talking point |
| --- | --- | --- | --- |
| 11900 S Morgan St (West Pullman) | 8 | Low | "No meaningful disruption. The explanation is brief and calm. Low confidence because the area has sparse data." |
| 3150 N Southport Ave (Lakeview) | 34 | Moderate | "One active building permit within 90 meters. Noise is Medium. Traffic is fine. Exactly the kind of heads-up a tenant would want before signing a lease." |
| 1600 W Chicago Ave (West Town) | 62 | High | *(already shown above)* |
| 1200 W Fulton Market (Fulton Market) | 81 | Severe | "Fulton Market has a multi-lane closure and an adjacent active construction site. Both signals reinforce each other. Severity is High across noise and traffic. This is an address you approach with eyes open." |

*Talking point after the table*: "The model never produces a Severe score from weak or distant evidence. It requires close, active, specific signals. That is the trust guarantee we build into the product."

---

## Part 4 — Why this is defensible (1–2 minutes)

**Say**: "Three things make this defensible."

1. **Free, official data.** Every signal in this model comes from Chicago's public Socrata APIs — the same sources city planners use. No scraping, no licensed feeds. The data is free, updated daily, and auditable.

2. **Interpretable output.** The model does not use a black-box algorithm. Every score can be explained in one or two dominant signals. That is intentional — buyers trust what they can audit, and regulators are paying attention to AI opacity in property decisions.

3. **API-first distribution.** We are not a portal. We are an API. That means any product team, any analyst workflow, any dispatch system can embed the score without switching platforms. The integration cost is one sprint.

---

## Part 5 — The ask (1 minute)

**Say**: "We are looking for design-partner customers and early capital to take this from a working demo to a production-grade API with SLAs."

"For CRE firms: a pilot at $300/month for 100 address lookups gives you enough signal to know whether this fits your diligence workflow. We will white-glove the onboarding and adjust the output format based on your feedback."

"For logistics operators: we want one dispatch-integrated pilot where we instrument a real address queue. You give us feedback on false positives. We give you a free month."

"For investors: the Chicago MVP is fully buildable within the current 8-week plan. The data pipeline is live. The API contract is locked. We are asking for the capital to finish it and sign the first three paying customers."

---

## Handling common objections

**"The data might not be accurate."**
The data comes directly from the City of Chicago's official permit and closure systems — the same sources used by city planners and published on the city's open data portal. We apply a confidence field to every response so buyers know when the evidence is strong versus when it is a weak or stale signal.

**"How is this different from just checking the city's permit portal?"**
The city portal is a raw database. It requires knowing what to search for, how to interpret permit types, how to assess distance and timing relevance, and how to aggregate multiple overlapping signals. Our API does all of that and returns a single interpretable number with context in under 500ms.

**"What happens when the data is out of date?"**
We run incremental ingestion daily and reflect data freshness in the `confidence` field. When evidence is stale, we say so explicitly — the score degrades toward Low and confidence drops to LOW rather than inventing false certainty.

**"Why only Chicago?"**
Chicago has some of the richest, most structured public construction data of any US city. Starting here lets us prove the model before expanding. The architecture is source-agnostic — adding a new city is a data pipeline problem, not a product redesign.
