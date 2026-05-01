# Project Brief: Livability Risk Engine

## One-line description
A multi-city disruption risk API that forecasts near-term construction impacts for a given address using public permit, closure, and infrastructure data where source coverage is available.

## Core problem
People and businesses lack a simple, forward-looking signal that quantifies near-term disruption risk (noise, traffic, pedestrian impacts) caused by nearby construction, utility work, and street closures. The problem is not Chicago-specific; source depth varies by city.

## MVP promise
Provide a reliable, repeatable risk score (0-100) for a single address in supported U.S. cities, reflecting imminent disruption from official permits, planned street closures, and related public infrastructure records.

## Target user
- City planners / infrastructure analysts who need quick situational awareness
- Operations teams (delivery, logistics, property managers) planning routes or staffing
- Early adopters in commercial real estate / mobility wanting a consistent disruption signal

## Output definition
A single disruption score (0-100) returned with confidence, severity, top risks, and a short explanation via a JSON API endpoint.

## Constraints
- Team size: 3 core humans + AI agents
- Timeline: 8-week MVP delivery horizon (prioritize first 2 weeks for data ingestion & API scaffold)
- City scope: multi-city U.S. coverage. Chicago remains the reference/deepest-coverage market, but the MVP may include additional cities when their source provenance, normalization, and caveats are documented.

## Explicit non-goals
- No promise of uniform national coverage or equal evidence depth across every city
- No predictive machine learning model requiring training on historical incident resolution
- No mobile app or consumer-facing UI beyond a simple frontend demo
- No paid third-party traffic/real-time vehicle-location feeds
