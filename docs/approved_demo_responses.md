# Approved Buyer-Facing Demo Responses
task: product-016
lane: product
approved: 2026-03-18

This document is the canonical source for approved demo responses.
One response per score band, locked for use in demos, walkthroughs,
stakeholder presentations, and frontend fallback copy.

References:
  - docs/03_scoring_model.md  (score bands, explanation rules, tone guidance)
  - docs/04_api_contracts.md  (response shape and field definitions)
  - docs/product_qa_review.md (QA source for these four addresses)
  - docs/product_qa_checklist.md (checklist each response was reviewed against)

Rules for using these responses:
  - Do not change field names, value types, or response shape.
  - Do not change the explanation wording without re-running the QA checklist.
  - Do not promote a Moderate example as a High example in demos.
  - top_risks strings are display-ready — the frontend renders them directly.
  - Use the address exactly as written; these are the canonical demo addresses.

---

## LOW BAND — Score 7
### 5800 N Northwest Hwy, Chicago, IL (Jefferson Park)

**When to use:** Show this when demonstrating that the engine produces calm,
non-alarming output for stable neighborhoods. Good for anchoring the low end
of the scale before showing a High or Severe example.

**Buyer takeaway:** This address has very little evidence of near-term
construction disruption. A buyer can expect mostly normal access and livability.

```json
{
  "address": "5800 N Northwest Hwy, Chicago, IL",
  "disruption_score": 7,
  "confidence": "LOW",
  "severity": {
    "noise": "LOW",
    "traffic": "LOW",
    "dust": "LOW"
  },
  "top_risks": [
    "Light permit activity in the surrounding area within roughly 300 meters"
  ],
  "explanation": "Little evidence of meaningful near-term disruption was found close to this address. Background permit activity exists in the area but is not expected to materially affect the near-term experience."
}
```

**QA checklist sign-off:**
- Score band (Low 0–24) matches explanation tone ✓
- "not expected to materially affect" is correctly calm for Low band ✓
- LOW confidence reflects faint, distant evidence ✓
- Single top_risk appropriate for weak evidence ✓
- No alarming language ✓
- No schema terms exposed ✓
- Passes all API contract checks ✓

---

## MODERATE BAND — Score 40
### 2500 W Armitage Ave, Chicago, IL (Logan Square)

**When to use:** Show this as the middle-ground example. Demonstrates that
the engine finds real signals in active neighborhoods without overstating risk.
Good for showing that "moderate" means noticeable, not alarming.

**Buyer takeaway:** Construction activity is present nearby and may produce
some noise disruption in the near term, but it is not expected to materially
disrupt daily life or access at this address.

```json
{
  "address": "2500 W Armitage Ave, Chicago, IL",
  "disruption_score": 40,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "MEDIUM",
    "traffic": "LOW",
    "dust": "LOW"
  },
  "top_risks": [
    "Active construction permit near 2500 W Armitage Ave within roughly 90 meters",
    "Nearby permitted activity adds a background noise signal",
    "Construction noise is the primary near-term disruption signal at this address"
  ],
  "explanation": "Nearby construction activity is the main driver, so this address has moderate short-term noise disruption. No closure or demolition was identified in the near-term window."
}
```

**QA checklist sign-off:**
- Score band (Moderate 25–49) matches explanation tone ✓
- "moderate short-term noise disruption" is appropriately noticeable-not-alarming ✓
- MEDIUM confidence reflects active, plausible evidence ✓
- noise MEDIUM justified by construction permit at ~90m (~14 weighted pts) ✓
- traffic LOW correct — no closure present ✓
- dust LOW correct — no demolition present ✓
- top_risks are plain-English and buyer-readable ✓
- Explanation correctly notes absence of closure/demolition ✓
- Passes all API contract checks ✓

---

## HIGH BAND — Score 62
### 1600 W Chicago Ave, Chicago, IL (West Town)

**When to use:** This is the primary demo address and the existing baseline
in the codebase. Use it first in any walkthrough. Demonstrates a clear,
concrete, decision-relevant disruption signal with a well-grounded explanation.

**Buyer takeaway:** A real lane closure nearby is elevating traffic disruption
at this address in the near term. A buyer should factor this into access
planning, delivery logistics, and day-to-day convenience expectations.

```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "disruption_score": 62,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "LOW",
    "traffic": "HIGH",
    "dust": "LOW"
  },
  "top_risks": [
    "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
    "Active closure window runs through 2026-03-22",
    "Traffic is the dominant near-term disruption signal at this address"
  ],
  "explanation": "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic disruption even though noise and dust are limited."
}
```

**QA checklist sign-off:**
- Score band (High 50–74) matches explanation tone ✓
- "elevated short-term traffic disruption" is clearly cautionary ✓
- MEDIUM confidence: active closure, specific dates, but not the highest
  precision evidence available ✓
- traffic HIGH justified by 2-lane closure at ~120m (~30 weighted pts) ✓
- noise LOW and dust LOW correct — no demolition/construction signal ✓
- top_risks include distance, active window, and dominant category label ✓
- Explanation is traffic-led, concise, deterministic ✓
- Passes all API contract checks ✓

**Note for demos:** This is also the demo-fallback response hardcoded in
`backend/app/main.py` and `frontend/src/lib/api.ts`. If no DB is configured,
this is what the frontend shows. Keep this response locked.

---

## SEVERE BAND — Score 75
### 1200 W Fulton Market, Chicago, IL (Fulton Market)

**When to use:** Use this as the dramatic anchor for the high end of the
scale — Chicago's most active construction corridor. Demonstrates that the
engine can surface genuinely severe disruption with clear, specific evidence.
Good for closing a demo after showing Low and High to show the full range.

**Buyer takeaway:** This address has multiple strong, active disruption
signals including a full street closure and demolition activity. A buyer
should expect the address to feel actively disrupted, not just occasionally
inconvenienced, in the near term.

```json
{
  "address": "1200 W Fulton Market, Chicago, IL",
  "disruption_score": 75,
  "confidence": "HIGH",
  "severity": {
    "noise": "HIGH",
    "traffic": "HIGH",
    "dust": "HIGH"
  },
  "top_risks": [
    "Full street closure on W Fulton Market within roughly 60 meters",
    "Active demolition permit near 1200 W Fulton Market within roughly 100 meters",
    "Both traffic and noise/dust signals are elevated at this address"
  ],
  "explanation": "A full street closure on Fulton Market within 60 meters is the dominant driver, so this address has severe near-term traffic disruption. Active demolition nearby also elevates noise and dust to high levels."
}
```

**QA checklist sign-off:**
- Score band (Severe 75–100) matches explanation tone ✓
- "severe near-term traffic disruption" is strongly cautionary without
  being absolute ✓
- HIGH confidence: full closure, specific location, active timing, close
  proximity — meets all HIGH evidence criteria ✓
- traffic HIGH: full closure at ~60m (~45 weighted pts, well above 25 threshold) ✓
- noise HIGH: demolition at ~100m (~24 weighted pts, above 18 threshold) ✓
- dust HIGH: demolition justifies dust elevation ✓
- top_risks name both dominant drivers; third bullet summarizes combined impact ✓
- Explanation leads with closure (dominant per tie-break rules), names
  demolition as secondary because it materially changes interpretation ✓
- "actively disrupted rather than occasionally inconvenienced" matches
  Severe band guidance in docs/03_scoring_model.md ✓
- Passes all API contract checks ✓

---

## DEMO FLOW GUIDANCE

### Recommended walkthrough order
1. **Start with High (W Chicago Ave, 62)** — it's the baseline, already in
   the frontend, and immediately shows the core product value proposition.
2. **Show Severe (Fulton Market, 75)** — escalate to show what "really bad"
   looks like. Emphasize HIGH confidence and all-HIGH severity.
3. **Show Low (Jefferson Park, 7)** — show the other end. Makes clear the
   engine is calibrated, not alarmist.
4. **Show Moderate (Logan Square, 40)** — close with the nuanced middle case.
   Demonstrates product maturity: not everything is high-risk.

### Key talking points per band
- **Low:** "The engine doesn't cry wolf. When there's no real signal, it says so."
- **Moderate:** "It finds real nearby activity and puts it in context — noticeable but not a dealbreaker."
- **High:** "This is what a decision-relevant disruption signal looks like. One clear driver, grounded explanation, actionable."
- **Severe:** "Multiple strong signals converging. HIGH confidence. All three severity dimensions elevated. This is when a buyer needs to know."

### Confidence as a trust signal
In demos, lead with confidence as the "why should I trust this" answer:
- LOW = "we found something but it's faint and distant"
- MEDIUM = "real evidence, plausible and recent, some ambiguity"
- HIGH = "specific, current, and directly tied to this address"

### What NOT to do in demos
- Do not show the all-LOW severity Moderate addresses (#8, #10, #11) as
  your primary Moderate example — they may confuse reviewers.
  Use Logan Square (#12) instead.
- Do not imply the score is a scientific forecast. Use language like
  "near-term disruption signal" and "practical indicator."
- Do not show Fulton Market first — it sets too high a baseline and
  makes everything else seem underwhelming.

---

## WORDING DECISIONS LOCKED BY THIS DOCUMENT

These product decisions are now final for the MVP and should not be
revisited without a cross-lane review.

1. **"disruption_score" is a "near-term disruption signal"** in buyer-facing
   copy, not a "score" or "rating." Avoids implying precision it does not have.

2. **"traffic" always means traffic and curb access** when curb or parking
   impacts are material to the nearby disruption story. Never just "congestion."

3. **Explanation tone ladder is fixed:**
   - Low: "not expected to materially affect"
   - Moderate: "moderate short-term [category] disruption"
   - High: "elevated short-term [category] disruption"
   - Severe: "severe near-term [category] disruption"

4. **HIGH confidence is rare.** In demo walkthroughs, point out that only
   Fulton Market gets HIGH — this is a feature, not a bug. It means the
   engine earns HIGH rather than giving it away.

5. **Explanation mentions a secondary driver only when it materially changes
   understanding.** Logan Square (Moderate) does not mention a secondary
   driver. Fulton Market (Severe) does. This asymmetry is intentional.
