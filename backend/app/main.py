from datetime import datetime, timezone

from fastapi import FastAPI, Query

app = FastAPI(title="Livability Risk Engine")


@app.get("/score")
def get_score(address: str = Query(..., description="Chicago address to score")) -> dict:
    return {
        "address": address,
        "location": {"lat": 41.895, "lon": -87.655},
        "score": 62,
        "confidence": "MEDIUM",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "projects": [
            {
                "project_id": "chicago_closures:12345",
                "title": "W Chicago Ave lane closure",
                "impact_type": "traffic",
                "distance_m": 120,
                "severity": 70,
                "start_date": "2026-03-18",
                "end_date": "2026-03-22",
                "notes": "2-lane closure, eastbound",
            }
        ],
        "explanation": "Top contributor is a 2-lane closure 120m away; permit status is active.",
    }
