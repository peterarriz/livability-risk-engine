from fastapi import FastAPI, Query

app = FastAPI(title="Livability Risk Engine")


@app.get("/score")
def get_score(address: str = Query(..., description="Chicago address to score")) -> dict:
    return {
        "address": address,
        "disruption_score": 62,
        "confidence": "MEDIUM",
        "severity": {
            "noise": "LOW",
            "traffic": "HIGH",
            "dust": "LOW",
        },
        "top_risks": [
            "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
            "Active closure window runs through 2026-03-22",
            "Traffic is the dominant near-term disruption signal at this address",
        ],
        "explanation": "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic disruption even though noise and dust are limited.",
    }
