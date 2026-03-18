# Scoring Model (MVP)

## Score structure
- Output: single integer `disruption_score` in range **0–100** (higher = higher near-term disruption risk).
- Score is based on simple MVP heuristics using nearby active closures and permit activity.
- For MVP, the response should emphasize the strongest near-term driver rather than a complex multi-factor breakdown.

## Score interpretation
These bands are meant to help a normal user understand what the headline score means in practical terms.

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

## Open questions
- What exact heuristic thresholds should convert raw inputs into numeric score bands without making the model look overfit?
- Should `traffic` in the API be explicitly described as including both traffic flow and curb/parking access friction in user-facing copy?
- Under what conditions should explanation copy mention a secondary driver instead of only the dominant one?
