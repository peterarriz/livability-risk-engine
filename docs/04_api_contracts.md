# API Contracts

## Canonical normalized project schema (example)
```json
{
  "project_id": "string",          // stable unique id (source + source_id)
  "source": "string",              // source system (e.g., "chicago_permits", "chicago_closures")
  "title": "string",               // short human label
  "description": "string",
  "category": "permit" | "closure" | "utility",
  "status": "active" | "pending" | "completed" | "unknown",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "geometry": {                      // GeoJSON Point/LineString/Polygon
    "type": "Point",
    "coordinates": [lng, lat]
  },
  "location_text": "string",       // original address/description
  "impact_type": "noise" | "traffic" | "pedestrian" | "mixed",
  "scale": {                         // normalized impact sizing
    "length_m": number,
    "lanes_closed": number | null,
    "permits_count": number | null
  },
  "updated_at": "YYYY-MM-DDTHH:MM:SSZ"
}
```

## `/score` endpoint request
```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "as_of": "2026-03-18T00:00:00Z" // optional, defaults to now
}
```

## `/score` endpoint response
```json
{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "location": { "lat": 41.895, "lon": -87.655 },
  "score": 62,
  "confidence": "MEDIUM",         // HIGH | MEDIUM | LOW
  "as_of": "2026-03-18T12:00:00Z",
  "projects": [
    {
      "project_id": "chicago_closures:12345",
      "title": "W Chicago Ave lane closure",
      "impact_type": "traffic",
      "distance_m": 120,
      "severity": 70,
      "start_date": "2026-03-18",
      "end_date": "2026-03-22",
      "notes": "2-lane closure, eastbound"
    }
  ],
  "explanation": "Top contributor is a 2-lane closure 120m away; permit status is active."
}
```
