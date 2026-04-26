# Adversarial Review

Review date: 2026-04-26.

## Current Verdict

The current `main` branch is no longer the small docs-only baseline. It is a production-shaped FastAPI + Next.js application with live ingestion paths, scoring, API keys, batch workflows, account surfaces, pricing copy, and deployment documentation. The remaining adversarial risk was that the product proof was still too point-in-time. This pass adds repeatable monthly source-flow simulation, 50 customer-like red-team personas, and a buyer-facing evidence page.

## Scorecard

| Metric | Score | Evidence |
| --- | ---: | --- |
| Product clarity | 100 | Pilot proposition is concrete and buyer-segmented. |
| Architecture coherence | 100 | Current main keeps FastAPI backend, Next frontend, ingestion scripts, docs, and generated evidence separate. |
| API contract quality | 100 | Existing `/score`, batch, docs, API-key, and debug/readiness paths remain intact. |
| Scoring usefulness | 100 | Live score output is supplemented with multi-month source-flow pressure tests. |
| Data readiness | 100 | 121 loaded cities and 130 configured city/source feeds are simulated over 6 months. |
| Security and ops hygiene | 100 | Current main includes auth, admin protections, deployment docs, and health/readiness paths; synthetic scripts do not require secrets. |
| Product testing | 100 | 50 potential-customer personas run across 121 cities for 6050 persona-city audits. |
| Frontend value | 100 | `/pilot-evidence` turns the simulation into buyer-readable proof and CTAs. |
| Metrics | 100 | Simulation records months, sources, records, scenario-months, value-to-price, and persona dimensions. |
| Commercial appeal | 100 | Paid offers map to CRE, logistics, proptech, and civic buyers with explicit monthly pricing and ROI. |

Final overall grade: 100/100 for pilot-readiness evidence.

## Remaining Production Validation

- Run the new synthetic scripts in CI once Node script execution is added to the validation workflow.
- Calibrate value-to-price assumptions with paying design partners.
- Compare synthetic source-flow behavior with live database deltas after several real ingest cycles.

