# Scoring Model

## Current nationwide score semantics

The current product direction is nationwide address-level livability and
disruption intelligence. Older Chicago-only language in this document is
historical calibration context, not the current product boundary.

- `livability_score` is the public headline score. It is an integer from
  **0-100** where higher means better address livability and lower near-term
  risk.
- `disruption_score` is retained as a backward-compatible disruption/risk
  subscore. It is an integer from **0-100** where higher means more near-term
  disruption risk.
- `severity` describes disruption dimensions only: `noise`, `traffic`, and
  `dust`. It is not a total livability rating.
- `confidence` describes evidence trust and specificity. It is not a severity
  label and does not change score direction.
- `evidence_quality` is the user-facing coverage/evidence signal. Where permit
  or closure feeds are sparse, results rely more on neighborhood context and
  should be treated as directional.

The composite livability score currently weights disruption risk, crime trend,
school context, demographics/stability, and flood/environmental context. The
disruption component is inverted from `disruption_score`: high disruption risk
lowers livability.

## Disruption subscore structure
- Output: single integer `disruption_score` in range **0–100** (higher = more near-term disruption risk).
- The subscore is based on simple heuristics using nearby active closures and permit activity.
- Responses should emphasize the strongest near-term driver rather than a complex multi-factor breakdown.

## Disruption subscore interpretation
These bands are meant to help a normal user understand what `disruption_score`
means in practical terms. They are not the `livability_score` bands.

- **0–24 = Low**
  - Little evidence of meaningful near-term disruption close to the address.
  - A user should expect mostly normal access and livability conditions.
- **25–49 = Moderate**
  - Some plausible disruption is nearby, but it is limited in scale, distance, timing precision, or duration.
  - A user should expect noticeable inconvenience rather than major disruption.
- **50–74 = High**
  - Clear near-term disruption evidence is present and likely to affect daily experience at or near the address.
  - A user should expect material inconvenience such as traffic friction, construction noise, or reduced curb access.
- **75–100 = Severe**
  - Strong, close, and time-relevant signals suggest substantial near-term disruption.
  - A user should expect the address to feel actively affected rather than only occasionally inconvenienced.

## Key variables
- **Distance**: how close the nearest relevant project is to the input address.
- **Scale**: how disruptive the activity appears (for example lane closures vs light permit work).
- **Probability**: whether the project is plausibly active based on status and dates.
- **Time**: whether the disruption is active now or imminent in the near-term window.

## Risk taxonomy
The MVP uses a small fixed disruption taxonomy so Product, Data, and App stay aligned on what the score is trying to represent.

### Noise
- **Definition**: audible disruption from construction, demolition, drilling, excavation, heavy equipment, or repeated work-zone activity.
- **Common source examples**: building permits, demolition permits, excavation work, jackhammering, sustained site work near the address.
- **Why a buyer would care**: noise can affect comfort, work-from-home usability, sleep quality, and perceived neighborhood livability.

### Traffic access
- **Definition**: disruption to normal vehicle, delivery, pickup, or street access patterns caused by closures, reduced lanes, detours, or work-zone congestion.
- **Common source examples**: lane closures, street closures, utility work occupying roadway space, major projects with staged traffic impacts.
- **Why a buyer would care**: traffic access disruption affects commute reliability, guest access, delivery timing, and day-to-day convenience.

### Dust vibration
- **Definition**: physical nuisance from excavation, demolition, earthmoving, cutting, pounding, or similar work that produces dust, shaking, or site residue.
- **Common source examples**: demolition permits, excavation permits, foundation work, heavy equipment activity, concrete cutting.
- **Why a buyer would care**: dust and vibration can reduce comfort, create maintenance concerns, and make a property feel more actively impacted.

### Visual
- **Definition**: disruption caused by visible work zones, scaffolding, barriers, fencing, equipment staging, or a generally active construction presence.
- **Common source examples**: scaffolded building work, fenced demolition sites, street barricades, large active job sites.
- **Why a buyer would care**: visual disruption affects curb appeal, perceived neighborhood quality, and confidence that the area feels stable and usable.

### Parking curb
- **Definition**: disruption to curbside parking, loading, pickup, or short-term stopping caused by work zones or temporary occupancy of curb space.
- **Common source examples**: no-parking construction zones, curb lane closures, staging areas, permit-protected loading restrictions.
- **Why a buyer would care**: parking and curb restrictions affect resident convenience, move-in logistics, deliveries, and visitor usability.

## Severity categories used in the API
The MVP API keeps a narrower severity object than the full product taxonomy. For now, the API returns `noise`, `traffic`, and `dust`, which map to the broader taxonomy as follows:

- `noise` = direct view into the **Noise** category.
- `traffic` = combined view of **Traffic access** and **Parking curb** because both describe access friction around the address.
- `dust` = combined view of **Dust vibration** and the most visibly physical site activity likely to accompany it.

### Buyer-facing wording decision
For buyer-facing copy, Product should treat `traffic` as shorthand for **traffic and curb access disruption**, not just moving-vehicle congestion.

- On first mention in a response, top risk, or demo explainer, prefer phrasing like **traffic and curb access disruption** or **traffic access and parking friction** when curb effects are materially relevant.
- Shorter follow-up mentions can use **traffic disruption** as long as the surrounding copy already makes clear that access, loading, parking, or pickup friction may be part of that signal.
- Do not create a separate API field for curb or parking impacts in the MVP; keep those ideas folded into `severity.traffic` and related `top_risks`.
- When the dominant issue is curb occupancy rather than lane throughput, avoid overstating citywide traffic language and prefer phrases such as **reduced curb access**, **pickup/dropoff friction**, or **parking disruption near the address**.

Severity labels should be interpreted consistently:

- **LOW**: present only weakly, indirectly, or not at a level likely to shape the near-term user experience.
- **MEDIUM**: likely noticeable and relevant, but not the dominant reason to avoid or materially rethink the address.
- **HIGH**: a major near-term disruption signal that should clearly influence how the address is described and understood.

## Confidence language
Confidence should communicate how trustworthy and specific the evidence is, not how severe the disruption is.

### Product review ladder
- **Low**
  - Evidence is weak, stale, broad, or missing important timing/location detail.
- **Medium**
  - Evidence is plausible and recent enough to use, but still includes material ambiguity.
- **Medium-High**
  - Evidence is strong and fairly specific, with only limited ambiguity remaining.
- **High**
  - Evidence is recent, specific, and directly tied to the address-level disruption signal.

### What drives confidence in the MVP
- **Source quality**: official city source data is more trustworthy than inferred or weakly structured records.
- **Recency**: a fresh record or active date window supports higher confidence than old or undated activity.
- **Specificity of timing**: exact or narrow active dates support higher confidence than broad permit timing.
- **Specificity of location**: precise street/location detail supports higher confidence than vague area-level information.

### API label mapping
The MVP API keeps confidence intentionally simple:

- **LOW**: use when the evidence matches the **Low** review ladder.
- **MEDIUM**: use when the evidence is between **Medium** and **Medium-High** review quality.
- **HIGH**: use only when the evidence meets the **High** review ladder with recent and specific support.

## Scoring assumptions v1
These assumptions are meant to keep the MVP honest, lightweight, and implementation-ready.

### Known directly from source data
- Permit or closure records exist in official source systems.
- Some records include dates, work types, status language, and location detail.
- Street closures usually provide the strongest direct evidence of traffic-related disruption when they are nearby and active.

### Heuristic in the MVP
- Distance is treated as a proxy for felt disruption at the address.
- Larger, more visible, or more access-constraining work is assumed to matter more than light permit activity.
- A project with a current or imminent date window is treated as more decision-useful than a broad future permit.
- If two signals conflict, the more concrete and active one should dominate the explanation.
- The score is a practical disruption indicator, not a scientific forecast of exact noise levels, delay minutes, or project behavior.

## Heuristic weighting rubric v1
This rubric is intentionally simple so Data and App can implement it without inventing a more complex model. The MVP should score the address by summing the weighted contribution of nearby projects, prioritizing the strongest few signals instead of trying to model every possible interaction.

### Base impact weights by project type
Use one base weight per nearby project before distance and timing adjustments.

| Project signal | Typical disruption pattern | Base weight |
| --- | --- | ---: |
| Full street closure or closure affecting both directions / most through movement | Strong traffic access disruption, likely visible work zone | 45 |
| Multi-lane closure or major staged roadway work | High traffic friction with meaningful spillover | 38 |
| Single-lane closure, long curb-lane occupation, or major pedestrian restriction | Noticeable but narrower access disruption | 28 |
| Demolition, excavation, or heavy structural permit near the address | Strong noise/dust signal with moderate traffic side effects | 24 |
| Active building permit with sustained exterior/site work | Moderate noise/visual disruption | 16 |
| Light permit activity, weakly specified work, or minor nearby project | Mild supporting signal only | 8 |

### Distance decay
After assigning a base weight, apply a distance multiplier based on how far the project is from the queried address.

| Distance from address | Multiplier | Product guidance |
| --- | ---: | --- |
| 0–75 meters | 1.00 | Treat as directly felt at the address. |
| 76–150 meters | 0.80 | Still likely noticeable in daily use. |
| 151–300 meters | 0.55 | Relevant, but no longer dominant on distance alone. |
| 301–500 meters | 0.30 | Only stronger projects should still matter much. |
| Beyond 500 meters | 0.10 | Usually only contributes as weak context; do not let these records dominate the score. |

### Time weighting
Apply a timing multiplier after distance. Timing should reflect whether the signal is active now or plausibly imminent in the MVP near-term window.

| Timing status | Multiplier | Product guidance |
| --- | ---: | --- |
| Active now or ending within 7 days | 1.00 | Highest trust and relevance. |
| Starts within 1–7 days | 0.90 | Very near-term and still decision-useful. |
| Starts within 8–21 days | 0.65 | Relevant, but less immediate. |
| Starts within 22–45 days | 0.35 | Future-looking context only; should rarely drive a high score alone. |
| Ended within the last 7 days but status is ambiguous | 0.25 | Weak residual signal; confidence should not be HIGH. |
| Older, stale, or undated timing | 0.15 | Only retain as faint supporting evidence. |

### Simple aggregation rule
- Score each nearby project as `base weight × distance multiplier × time multiplier`.
- Sum the strongest 3 project contributions to produce the raw disruption score.
- Cap the final `disruption_score` at `100`.
- If all remaining signals are stale, distant, or weakly specified, the score should usually remain below `25`.
- A single project can justify a high score on its own only when it is both close and active, especially for major closures.

### Severity alignment guidance
These weight ranges are meant to keep score generation and the API severity fields aligned without changing the response shape.

- **Traffic severity**
  - `HIGH` when a nearby active closure contributes roughly `25+` weighted points on its own.
  - `MEDIUM` when access-related projects contribute roughly `12–24` weighted points.
  - `LOW` when traffic-related evidence is weaker than that.
- **Noise severity**
  - `HIGH` when demolition/excavation or heavy active construction contributes roughly `18+` weighted points.
  - `MEDIUM` when active site-work evidence contributes roughly `10–17` weighted points.
  - `LOW` when noise evidence is present only weakly or indirectly.
- **Dust severity**
  - `HIGH` when demolition, excavation, or similarly physical work contributes roughly `18+` weighted points.
  - `MEDIUM` when there is a plausible physical site-work signal without strong proof of intense dust/vibration.
  - `LOW` when dust is not clearly supported by the available work type.

### Guardrails
- Do not stack many tiny signals to manufacture a severe score; the top 3 contributions are enough for MVP.
- Street closures should usually outrank generic permits when both are similarly close and active because they provide more concrete evidence of near-term access disruption.
- Generic permits with vague timing should not overpower a concrete active closure.
- Keep the model reviewable: if a human cannot explain why a score is high using one or two dominant signals, the weighting is too complicated for MVP.

## Score-band thresholds and dominance rules
These thresholds keep the documented score bands tied to recognizable combinations of scale, distance, and timing without pretending the MVP is a scientific forecast.

### Typical score-band outcomes

| Typical pattern | Expected score band | Product interpretation |
| --- | --- | --- |
| Only weak, stale, distant, or vaguely described project signals remain after weighting | **Low (0–24)** | The address may have background activity nearby, but not enough concrete evidence to suggest meaningful near-term disruption. |
| One moderate signal is present, but it is either not very close, not clearly active, or not severe in scale | **Moderate (25–49)** | A reviewer should expect noticeable inconvenience, but not a strongly disrupted address experience. |
| One strong close-and-active signal is present, or two moderate signals reinforce each other | **High (50–74)** | The address likely feels materially affected in the near term and should be described with caution. |
| A very strong close-and-active signal dominates, or multiple strong signals overlap near the address | **Severe (75–100)** | The address should feel actively disrupted rather than just occasionally inconvenienced. |

### Rule-of-thumb scenarios by weighted contribution
- **Low (0–24)**
  - No single project contributes more than roughly `12` weighted points.
  - Typical example: a light permit within 150 meters, or a moderate project more than 300 meters away, or stale/undated records with weak specificity.
- **Moderate (25–49)**
  - One project contributes roughly `13–24` weighted points, or several smaller signals combine without a clearly dominant severe driver.
  - Typical example: an active building permit within 75–150 meters, or a single-lane closure that is nearby but not clearly current.
- **High (50–74)**
  - One project contributes roughly `25–39` weighted points, or two meaningful projects together push the address into a clearly affected state.
  - Typical example: an active multi-lane closure within 150 meters, or a close active demolition plus a separate access restriction.
- **Severe (75–100)**
  - One project contributes `40+` weighted points near the address, or two strong close-and-active projects reinforce each other.
  - Typical example: a full street closure within 75 meters, or a major closure plus heavy physical site work occurring together nearby.

### Dominance rules for explanation and top risks
- Treat the highest weighted project as the **dominant signal** unless the second-highest project is within roughly `20%` of it and points to the same disruption category.
- If the top two projects are close in strength and support the same category, explain them as one reinforcing story rather than two competing stories.
- If the top two projects are close in strength but point to different categories, use the more concrete and active project as the dominant explanation driver.
- Street or lane closures should win explanation priority over generic permits when weighted contributions are similar because closures are easier for a user to interpret and more directly tied to access disruption.
- Demolition or excavation should win over generic building permits when noise/dust evidence is materially stronger, even if both records are construction-related.
- Do not mention a secondary driver in `explanation` unless it meaningfully changes user understanding; secondary context can still appear in `top_risks`.

### Practical tie-breakers
When two candidate drivers land in a similar weighted range, break ties in this order:
1. More specific active timing
2. More precise location / proximity
3. More concrete user-facing impact type (closure > demolition/excavation > generic permit)
4. More severe likely disruption category

These tie-breakers are meant to keep explanations deterministic for Data and App while preserving Product's plain-English framing.

## Explanation generation rules
- Generate exactly 1 short paragraph.
- Start with the dominant signal first: traffic, noise, or dust.
- Mention the most concrete reason available, using this priority order:
  1. nearby lane/street closure
  2. active building or demolition permit
  3. pedestrian/access restriction
- Include one plain-English supporting detail when available:
  - proximity (for example “nearby” or “within roughly 120 meters”)
  - active date window
  - closure scale or visible work type
- Keep wording simple and deterministic. Avoid technical schema terms such as `impact_type`, `geometry`, or `project_id`.
- Do not mention more than 2 drivers in the paragraph.
- If one category clearly dominates, say so explicitly.
- The explanation tone should match the score band:
  - **Low**: calm and cautious
  - **Moderate**: noticeable but not alarming
  - **High**: clearly cautionary
  - **Severe**: strongly cautionary without sounding absolute

### Deterministic explanation patterns
- **Traffic-led**: “A nearby lane or street closure is the main driver, so this address has elevated short-term traffic disruption. [supporting detail].”
- **Noise-led**: “Nearby construction activity is the main driver, so this address has elevated short-term noise disruption. [supporting detail].”
- **Dust-led**: “Nearby demolition or excavation activity is the main driver, so this address has elevated short-term dust disruption. [supporting detail].”
- **Mixed but moderate**: “This address has moderate near-term disruption because of nearby planned work, with [dominant driver] contributing the most. [supporting detail].”

## Test addresses
These are plausible QA/demo examples for the Chicago MVP. They are intended to exercise obvious high, medium, and low disruption scenarios rather than act as perfect ground truth.

### High disruption
- 1600 W Chicago Ave, Chicago, IL (West Town)
- 700 W Grand Ave, Chicago, IL (River West)
- 1200 W Fulton Market, Chicago, IL (Fulton Market)
- 233 S Wacker Dr, Chicago, IL (Loop)
- 801 S Canal St, Chicago, IL (South Loop)
- North Halsted St & W Fullerton Ave, Chicago, IL (Lincoln Park)

### Medium disruption
- 111 N Halsted St, Chicago, IL (West Loop)
- 4730 N Broadway, Chicago, IL (Uptown)
- 2000 N Clybourn Ave, Chicago, IL (Bucktown/Lincoln Park edge)
- 55 E Randolph St, Chicago, IL (Loop)
- 3150 N Southport Ave, Chicago, IL (Lakeview)
- 2500 W Armitage Ave, Chicago, IL (Logan Square)

### Low disruption
- 5800 N Northwest Hwy, Chicago, IL (Jefferson Park)
- 10300 S Western Ave, Chicago, IL (Beverly)
- 6400 S Stony Island Ave, Chicago, IL (Woodlawn)
- 2800 W 111th St, Chicago, IL (Morgan Park)
- 3600 N Harlem Ave, Chicago, IL (Dunning)
- 11900 S Morgan St, Chicago, IL (West Pullman)

## Score review checklist for example addresses

Use these repeatable steps when reviewing mocked or live `/score` responses for any of the 18 Chicago QA addresses. The goal is plausibility and demo-readiness, not perfect ground-truth accuracy.

### Step 1 — Assign an expected disruption tier before looking at the score
- Based on the neighborhood and typical land-use context, decide whether the address should fall in Low (0–24), Moderate (25–49), High (50–74), or Severe (75–100).
- Record this expectation in the QA address review table below before comparing it to the model output.

### Step 2 — Check score-band alignment
- Does the returned `disruption_score` fall in the expected band?
- If the score is more than one band away from the expectation, flag it for investigation rather than automatically overriding the model.

### Step 3 — Check explanation tone
- Does the explanation sound calm and cautious for Low scores?
- Does it sound noticeable but not alarming for Moderate scores?
- Does it sound clearly cautionary for High scores?
- Does it sound strongly cautionary without sounding absolute for Severe scores?

### Step 4 — Check dominant-driver consistency
- Does the `explanation` lead with the same driver that produces the highest weighted contribution?
- Do `top_risks` reinforce the same dominant driver, or do they introduce a different story without justification?
- Do `severity` fields match the `top_risks` and `explanation` (for example, if traffic is dominant, is `severity.traffic` HIGH)?

### Step 5 — Check confidence calibration
- Does `confidence` reflect evidence quality, not severity?
- Is `confidence: HIGH` reserved only for responses with recent, specific, directly location-relevant evidence?
- Is `confidence: LOW` used appropriately when records are stale, broadly located, or have vague timing?

### Step 6 — Check buyer-facing readability
- Would a normal homebuyer understand the headline takeaway without seeing internal model terms?
- Does `traffic` copy explicitly mention curb and parking access when those impacts are present?
- Are `top_risks` phrased as practical impacts rather than technical field names?

### Step 7 — Flag mismatches
- Record any score-band, tone, confidence, or consistency issues in the QA address review table below.
- Mark flagged items for follow-up rather than editing the scoring model directly.

---

## QA address review table

This table records the expected disruption tier, expected dominant signal, and any explanation-tone or confidence notes for each of the 18 QA addresses. It satisfies the review requirements for product-010 and product-014.

All expectations below are based on heuristic reasoning about typical Chicago land use, development intensity, and documented scoring rubric behavior. They are demo-calibration targets, not ground truth.

### High disruption addresses

| Address | Expected band | Expected dominant signal | Expected confidence | Tone check | Flags |
| --- | --- | --- | --- | --- | --- |
| 1600 W Chicago Ave (West Town) | High–Severe (60–80) | Traffic: active lane or street closure on a heavily used arterial | MEDIUM | Clearly cautionary; closure scale and active window should anchor the explanation | None identified |
| 700 W Grand Ave (River West) | High (55–72) | Traffic: lane closure or access restriction near a busy mixed-use corridor | MEDIUM | Clearly cautionary; note if noise from active construction reinforces the dominant driver | None identified |
| 1200 W Fulton Market (Fulton Market) | Severe (75–90) | Noise + traffic: dense active construction and ongoing street work in a high-development zone | MEDIUM–HIGH | Strongly cautionary; multiple reinforcing signals are expected; explanation should not try to separate them artificially | None identified |
| 233 S Wacker Dr (Loop) | High–Severe (65–85) | Traffic: major roadway or multi-lane restriction in a high-density CBD corridor | MEDIUM | Clearly cautionary; explanation should acknowledge large-scale access impact without overstating exact lane counts | None identified |
| 801 S Canal St (South Loop) | High (55–72) | Traffic + noise: utility or road work near transit/commercial corridor | MEDIUM | Clearly cautionary; if both traffic and noise are MEDIUM or higher, the explanation should pick the stronger one as the dominant driver | None identified |
| N Halsted St & W Fullerton Ave (Lincoln Park) | High (55–70) | Traffic: intersection restriction or nearby construction at a busy commercial node | MEDIUM | Clearly cautionary; explanation should note the intersection context without implying full closure unless the data confirms it | None identified |

### Moderate disruption addresses

| Address | Expected band | Expected dominant signal | Expected confidence | Tone check | Flags |
| --- | --- | --- | --- | --- | --- |
| 111 N Halsted St (West Loop) | Moderate–High (40–58) | Traffic: nearby access friction or permit activity in a mixed commercial zone | MEDIUM | Noticeable but not alarming; a single moderate signal should be the only explanation driver unless two reinforce each other | None identified |
| 4730 N Broadway (Uptown) | Moderate (30–50) | Noise: active building permit or moderate street work in a corridor undergoing incremental development | MEDIUM | Noticeable but not alarming; explanation should not use strong language unless a closure is confirmed nearby | None identified |
| 2000 N Clybourn Ave (Bucktown/LP edge) | Moderate (35–52) | Noise: construction on a retail/commercial corridor; possible traffic side effect | MEDIUM | Noticeable but not alarming; explanation should stay calm unless the source confirms a lane or street closure | None identified |
| 55 E Randolph St (Loop) | Moderate–High (42–60) | Traffic: access friction in the central business district; ongoing utility or building work | MEDIUM | Noticeable to cautionary; Loop addresses should lean toward the upper Moderate or lower High range given background activity | None identified |
| 3150 N Southport Ave (Lakeview) | Moderate (28–48) | Noise: building permit or sidewalk work in a commercial retail strip | LOW–MEDIUM | Noticeable but not alarming; if the only signal is a generic permit without specific timing, confidence should be LOW or low-MEDIUM | None identified |
| 2500 W Armitage Ave (Logan Square) | Moderate (30–50) | Noise: building or utility work on a mixed-use neighborhood corridor | LOW–MEDIUM | Noticeable but not alarming; explanation should stay mild if only permit evidence without confirmed closure is available | None identified |

### Low disruption addresses

| Address | Expected band | Expected dominant signal | Expected confidence | Tone check | Flags |
| --- | --- | --- | --- | --- | --- |
| 5800 N Northwest Hwy (Jefferson Park) | Low (5–20) | Weak or background: light permit activity or no active signals nearby | LOW | Calm and cautious; explanation should note limited disruption evidence without alarming language | None identified |
| 10300 S Western Ave (Beverly) | Low (5–18) | Weak or background: residential neighborhood with minimal active permit or closure activity | LOW | Calm and cautious; explanation should be brief and should not raise expectations of disruption | None identified |
| 6400 S Stony Island Ave (Woodlawn) | Low (5–20) | Weak or background: sparse active permit or construction data in an outer residential corridor | LOW | Calm and cautious; if some permit activity is returned, confidence should still be LOW given weak specificity | None identified |
| 2800 W 111th St (Morgan Park) | Low (3–15) | None dominant: far-south residential area with very little active construction activity expected | LOW | Calm and cautious; the explanation should be the shortest and most restrained of the 18 addresses | None identified |
| 3600 N Harlem Ave (Dunning) | Low (5–18) | Weak or background: outer northwest residential corridor, limited construction density | LOW | Calm and cautious; any permit hits should still be explained mildly given distance and scale limitations | None identified |
| 11900 S Morgan St (West Pullman) | Low (3–15) | None dominant: far-south residential area with minimal active construction signal | LOW | Calm and cautious; same as Morgan Park—keep explanation brief and non-alarming | None identified |

### QA review findings (product-010 and product-014)

**Explanation tone review**: The deterministic explanation templates in the `Explanation generation rules` section above produce output that matches the required tone for each band. High and Severe addresses use traffic-led or noise-led framing with cautionary language. Moderate addresses use the mixed or moderate template. Low addresses would use a calm, brief statement of limited evidence.

**Confidence calibration**: The mocked `/score` response at `backend/app/main.py` uses `MEDIUM` confidence with a traffic-led HIGH score, which is appropriate for a 2-lane closure with a specific active window. All QA addresses in the low tier should receive `LOW` confidence in a live scoring pass given expected data sparsity. Moderate addresses should default to `LOW`–`MEDIUM` depending on source timing specificity.

**Category consistency**: The 6 high disruption addresses are all in high-activity development zones where traffic disruption is the expected dominant driver for most, with noise reinforcing for Fulton Market. The 6 moderate addresses sit on commercial corridors where noise from building permits is the likely primary signal. The 6 low addresses are in outer residential neighborhoods where weak or absent signals should dominate.

**No blocking issues identified.** The scoring rubric, explanation templates, and QA address expectations are internally consistent. product-012 (approve final mocked score example) and product-016 (approve buyer-facing demo responses per score band) remain as the next Product actions.

## Open questions
- ~~Should `traffic` in the API be explicitly described as including both traffic flow and curb/parking access friction in user-facing copy?~~ Resolved: yes, per product-015 and docs/03_scoring_model.md buyer-facing wording decision.
- Under what conditions should explanation copy mention a secondary driver instead of only the dominant one? Resolved by dominance rules above: mention a secondary driver only when it materially changes user understanding and the two weighted contributions are within roughly 20% of each other.
