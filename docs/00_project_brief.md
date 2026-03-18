# Project Brief: Livability Risk Engine (Chicago MVP)

## One-line description
A disruption risk API that forecasts near-term construction impacts for a given Chicago address using public permit, closure, and infrastructure data.

## Core problem
People and businesses in Chicago lack a simple, forward-looking signal that quantifies the near-term disruption risk (noise, traffic, pedestrian impacts) caused by nearby construction, utility work, and street closures.

## MVP promise
Provide a reliable, repeatable risk score (0–100) for any Chicago address that reflects imminent disruption from official permits and planned street/utility closures.

## Target user
- City planners / infrastructure analysts who need quick situational awareness
- Operations teams (delivery, logistics, property managers) planning routes or staffing
- Early adopters in commercial real estate / mobility wanting a consistent disruption signal

## Output definition
A single disruption score (0–100) returned with confidence, severity, top risks, and a short explanation via a JSON API endpoint.

## Constraints
- Team size: 3 core humans + AI agents
- Timeline: 8-week MVP delivery horizon (prioritize first 2 weeks for data ingestion & API scaffold)
- City scope: Chicago only (Cook County permit/closure sources)

## Explicit non-goals
- No multi-city or national rollout
- No predictive machine learning model requiring training on historical incident resolution
- No mobile app or consumer-facing UI beyond a simple frontend demo
- No paid third-party traffic/real-time vehicle-location feeds
