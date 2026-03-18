# Scoring Model (MVP)

## Score structure
- Output: single integer `disruption_score` in range **0–100** (higher = higher disruption risk).
- Score is based on simple MVP heuristics using nearby active closures and permit activity.
- For MVP, the response should emphasize the strongest near-term driver rather than a complex multi-factor breakdown.

## Key variables
- **Distance**: how close the nearest relevant project is to the input address.
- **Scale**: how disruptive the activity appears (for example lane closures vs light permit work).
- **Probability**: whether the project is plausibly active based on status and dates.
- **Time**: whether the disruption is active now or imminent in the near-term window.

## Severity categories (MVP)
1. **Noise**: building activity, demolition, jackhammering, general construction nuisance.
2. **Traffic**: lane closures, road work, detours, reduced vehicle throughput.
3. **Dust**: excavation, demolition, heavy construction, visible site activity.

## Confidence model
- `HIGH`: source is recent, specific, and clearly active.
- `MEDIUM`: source is plausible and recent enough, but some details are broad or inferred.
- `LOW`: source is stale, incomplete, or only weakly tied to active disruption.

## Important assumptions
- A project with a current or imminent date window is more important than a broad future permit.
- Street closures should usually dominate traffic severity when they are close to the address.
- Small permits can raise noise or dust but should not overwhelm the score unless there is a strong nearby signal.
- The score is a relative disruption indicator, not a prediction of accidents or exact travel delay.

## Explanation Generation Rules
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

### Deterministic explanation patterns
- **Traffic-led**: “A nearby lane or street closure is the main driver, so this address has elevated short-term traffic disruption. [supporting detail].”
- **Noise-led**: “Nearby construction activity is the main driver, so this address has elevated short-term noise disruption. [supporting detail].”
- **Dust-led**: “Nearby demolition or excavation activity is the main driver, so this address has elevated short-term dust disruption. [supporting detail].”
- **Mixed but moderate**: “This address has moderate near-term disruption because of nearby planned work, with [dominant driver] contributing the most. [supporting detail].”

## Test Addresses
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
- What exact thresholds should map raw heuristics to `LOW`, `MEDIUM`, and `HIGH` severity labels?
- When both a closure and a permit are present, should the explanation ever mention both if the closure is clearly dominant?
- How much date precision is required before confidence should move from `MEDIUM` to `HIGH`?
