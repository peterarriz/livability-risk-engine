# Frequently Asked Questions

Answers to the most common questions from investors, design-partner prospects, and buyers. All answers are consistent with the approved demo script (`docs/demo_script.md`) and pitch narrative (`docs/pitch_narrative.md`). No answer promises features outside the Chicago MVP scope.

---

## About the data

**Q: Where does the data come from?**

The Livability Risk Engine sources data from the City of Chicago's official public data portal at `data.cityofchicago.org`, specifically the building permit and street closure datasets published by the city and updated daily. These are the same records used by city planners, permit inspectors, and infrastructure teams. We ingest them daily via the Socrata API.

---

**Q: How current is the data?**

The permit and closure data is refreshed daily. The typical lag between a new permit being issued or a closure being recorded in the city system and appearing in our API is 24–48 hours. We reflect this in the `confidence` field — when a record is very recent, confidence can be higher; when data appears stale or undated, confidence is appropriately lower.

---

**Q: How accurate is the disruption score?**

The score is a practical near-term indicator, not a scientific forecast. It uses a rule-based model that weights the distance, scale, and timing of nearby permit and closure records. For addresses with specific, recent, well-located records (like an active multi-lane closure within 100 meters), the score is highly reliable. For addresses with sparse or vaguely located data, the score will be lower-confidence and the explanation will say so explicitly. We do not manufacture false certainty.

---

**Q: What happens if there is no permit or closure data near an address?**

The API returns a low disruption score (typically 0–15) with `confidence: LOW` and an explanation noting that no meaningful near-term disruption evidence was found. A low score does not mean the address is problem-free — it means the available city data does not currently show disruption signals near that location.

---

**Q: Does the score include utility work, CTA disruptions, or traffic incidents?**

Not in the current MVP. The score is based on building permits and planned street closures from the City of Chicago. Utility outages (ComEd, Peoples Gas), CTA schedule changes, and real-time traffic incidents are not included. We document this limitation clearly so buyers understand what is and is not in the signal.

---

**Q: What Chicago neighborhoods have the best data coverage?**

Coverage is generally better in neighborhoods with higher construction activity and more complete permit filing — the Loop, Near North Side, West Town, Fulton Market, Lincoln Park, and Wicker Park tend to have more records and more specific location data. Outer residential neighborhoods (Beverly, Morgan Park, West Pullman, Dunning) have sparser permit data, which results in lower-confidence scores for those areas.

---

## About the score

**Q: What does a score of 62 actually mean?**

A score of 62 puts an address in the High band (50–74). It means there is clear near-term disruption evidence that is likely to affect daily experience at or near the address — material inconvenience such as traffic friction, construction noise, or reduced curb access. It does not mean the address is unlivable or unusable; it means a buyer or tenant should factor the disruption into their decision with eyes open.

---

**Q: Can the score change day to day?**

Yes. As new permits are issued, closures are added or removed, and active date windows pass, the weighted evidence changes. A score can move meaningfully if a major closure is added nearby or if a previously active closure ends. This is by design — the score reflects current conditions, not a historical average.

---

**Q: Why does the score sometimes seem lower than I expected for a busy address?**

The score reflects the *official* data we have, not everything happening on the ground. A busy construction block with no permit filed or no street closure recorded will score lower than its ground-truth disruption level. If you believe a location has active disruption that the score is not capturing, it is likely that the disruption is either unpermitted or not yet recorded in the city system.

---

## About the product

**Q: How do I integrate the API?**

One GET request: `GET /score?address=<Chicago address string>`. The response is JSON with five fields: `disruption_score`, `confidence`, `severity`, `top_risks`, and `explanation`. No authentication is required for demo access. Paid tiers require an API key included in the request header. Full integration typically takes less than one engineer-day.

---

**Q: Is the API available for bulk address scoring?**

The Professional and Enterprise tiers support batch CSV submission for up to 100 addresses per request. Spot-tier users can call the API in a loop for bulk lookups. A dedicated batch endpoint is on the post-MVP roadmap.

---

**Q: Do you cover cities outside Chicago?**

No. The MVP is Chicago-only. The architecture is source-agnostic — adding a new city is a data pipeline decision, not a product redesign — but the Chicago dataset and scoring model are the focus for this phase. Multi-city expansion is a post-MVP priority, not a current commitment.

---

**Q: Is the API reliable enough for production use?**

The MVP is production-grade in terms of response time and output structure, but it does not yet include a formal uptime SLA. Enterprise contracts include an SLA. Design-partner pilots and Spot/Professional tiers should treat the API as a high-quality beta: stable, but without a contractual uptime guarantee.

---

## About pricing and pilots

**Q: How does pricing work?**

Three tiers: Spot ($0.10/call, usage-based), Professional ($299/month, 1,000 calls included), and Enterprise (from $1,500/month, custom volume and SLA). Full details are in `docs/pricing_model.md`.

---

**Q: What does the design-partner pilot include?**

Free API access for 30 days (up to 500 lookups), a 30-minute onboarding call, and a direct support channel. In exchange, we ask for a midpoint feedback session and a written summary at the end. Full terms in `docs/pilot_terms.md`.

---

**Q: Do you share individual address scores or aggregate neighborhood data?**

We only score the specific address requested. We do not build or sell neighborhood heatmaps, block-level aggregates, or trend reports in the MVP. That is a post-MVP product direction.
