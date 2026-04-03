"use client";

import React, { FormEvent, useState } from "react";

// ---------------------------------------------------------------------------
// Live API tester
// ---------------------------------------------------------------------------
function ApiTester() {
  const [testAddress, setTestAddress] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [testLoading, setTestLoading] = useState(false);

  async function handleTest(e: FormEvent) {
    e.preventDefault();
    if (!testAddress.trim()) return;
    setTestLoading(true);
    setTestResult(null);
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
      const url = `${base}/score?address=${encodeURIComponent(testAddress.trim())}`;
      const res = await fetch(url);
      const data = await res.json();
      setTestResult(JSON.stringify(data, null, 2));
    } catch (err) {
      setTestResult(`Error: ${err instanceof Error ? err.message : "Request failed"}`);
    } finally {
      setTestLoading(false);
    }
  }

  return (
    <div className="api-tester">
      <form onSubmit={handleTest} className="api-tester-form">
        <input
          type="text"
          value={testAddress}
          onChange={(e) => setTestAddress(e.target.value)}
          placeholder="1600 W Chicago Ave, Chicago, IL"
          className="api-tester-input"
        />
        <button type="submit" disabled={testLoading} className="api-tester-btn">
          {testLoading ? "Fetching..." : "Test"}
        </button>
      </form>
      {testResult && (
        <pre className="api-tester-result">{testResult}</pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Docs page
// ---------------------------------------------------------------------------
const SECTIONS = [
  { id: "auth", label: "Authentication" },
  { id: "endpoint", label: "Endpoint Reference" },
  { id: "response", label: "Response Fields" },
  { id: "examples", label: "Code Examples" },
  { id: "rates", label: "Rate Limits" },
  { id: "tester", label: "Live Tester" },
  { id: "coverage", label: "Coverage" },
] as const;

export default function ApiDocsPage() {
  return (
    <div className="docs-layout">
      {/* Left nav */}
      <nav className="docs-nav" aria-label="Documentation sections">
        <p className="docs-nav-title">API Docs</p>
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="docs-nav-link">{s.label}</a>
        ))}
        <a href="/" className="docs-nav-link docs-nav-back">&larr; Back to app</a>
      </nav>

      {/* Main content */}
      <main className="docs-main">
        <h1 className="docs-title">Livability Intelligence API</h1>
        <p className="docs-intro">
          Score any US address for livability using 20+ live data sources. Returns a 0&ndash;100 score,
          severity breakdown, top risk signals, and spatial context &mdash; all in a single JSON response.
        </p>

        {/* ── Authentication ─────────────────────────────────────── */}
        <section id="auth" className="docs-section">
          <h2>Authentication</h2>
          <p>
            All API requests require an API key passed in the <code>X-API-Key</code> header.
            Get your key from the <a href="/api-access">API Access page</a> after signing in.
          </p>
          <pre className="docs-code">{`curl -H "X-API-Key: lre_your_key_here" \\
  "https://api.livabilityrisks.com/score?address=1600+W+Chicago+Ave,+Chicago,+IL"`}</pre>
          <p className="docs-note">
            Unauthenticated requests work for testing but are heavily rate-limited.
            We recommend always including your API key.
          </p>
        </section>

        {/* ── Endpoint Reference ──────────────────────────────────── */}
        <section id="endpoint" className="docs-section">
          <h2>Endpoint Reference</h2>
          <div className="docs-endpoint-block">
            <span className="docs-method">GET</span>
            <code>/score?address=&#123;address&#125;</code>
          </div>
          <h3>Parameters</h3>
          <table className="docs-table">
            <thead><tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
            <tbody>
              <tr><td><code>address</code></td><td>string</td><td>Yes</td><td>Full US street address including city and state</td></tr>
            </tbody>
          </table>

          <h3>Sample Response</h3>
          <pre className="docs-code">{`{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "disruption_score": 62,
  "livability_score": 48,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "HIGH",
    "traffic": "MEDIUM",
    "dust": "LOW"
  },
  "top_risks": [
    "A 2-lane closure within roughly 120 meters...",
    "Active construction permit at 1620 W Chicago Ave..."
  ],
  "explanation": "Two active disruption signals detected...",
  "mode": "live",
  "latitude": 41.8956,
  "longitude": -87.6606,
  "nearby_signals": [ ... ],
  "livability_breakdown": {
    "components": {
      "disruption_risk": { "raw_score": 38, "weighted_contribution": 13.3 },
      "crime_trend": { "raw_score": 55, "weighted_contribution": 13.8 },
      "school_rating": { "raw_score": 60, "weighted_contribution": 12.0 }
    }
  }
}`}</pre>
        </section>

        {/* ── Response Fields ─────────────────────────────────────── */}
        <section id="response" className="docs-section">
          <h2>Response Fields</h2>
          <table className="docs-table">
            <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
            <tbody>
              <tr><td><code>address</code></td><td>string</td><td>The geocoded address</td></tr>
              <tr><td><code>disruption_score</code></td><td>integer</td><td>0&ndash;100 construction disruption activity score</td></tr>
              <tr><td><code>livability_score</code></td><td>integer</td><td>0&ndash;100 composite livability score (includes crime, schools, environment)</td></tr>
              <tr><td><code>confidence</code></td><td>string</td><td>LOW, MEDIUM, or HIGH &mdash; how closely signals tie to this specific address</td></tr>
              <tr><td><code>severity</code></td><td>object</td><td>Three-axis severity: <code>noise</code>, <code>traffic</code>, <code>dust</code> (each LOW/MEDIUM/HIGH)</td></tr>
              <tr><td><code>top_risks</code></td><td>string[]</td><td>Plain-English descriptions of the top disruption signals</td></tr>
              <tr><td><code>explanation</code></td><td>string</td><td>Summary paragraph explaining the score</td></tr>
              <tr><td><code>mode</code></td><td>string</td><td><code>live</code> (real data) or <code>demo</code> (estimated)</td></tr>
              <tr><td><code>latitude</code>, <code>longitude</code></td><td>number</td><td>Geocoded coordinates</td></tr>
              <tr><td><code>nearby_signals</code></td><td>array</td><td>Active permits, closures, and incidents within scoring radius</td></tr>
              <tr><td><code>livability_breakdown</code></td><td>object</td><td>Component scores: disruption_risk, crime_trend, school_rating, demographics, flood risk</td></tr>
            </tbody>
          </table>
        </section>

        {/* ── Code Examples ───────────────────────────────────────── */}
        <section id="examples" className="docs-section">
          <h2>Code Examples</h2>

          <h3>curl</h3>
          <pre className="docs-code">{`curl -s -H "X-API-Key: lre_your_key_here" \\
  "https://api.livabilityrisks.com/score?address=700+W+Grand+Ave,+Chicago,+IL" \\
  | python3 -m json.tool`}</pre>

          <h3>Python</h3>
          <pre className="docs-code">{`import requests

resp = requests.get(
    "https://api.livabilityrisks.com/score",
    params={"address": "700 W Grand Ave, Chicago, IL"},
    headers={"X-API-Key": "lre_your_key_here"},
)
data = resp.json()
print(f"Livability: {data['livability_score']}/100")
print(f"Confidence: {data['confidence']}")`}</pre>

          <h3>JavaScript (fetch)</h3>
          <pre className="docs-code">{`const res = await fetch(
  "https://api.livabilityrisks.com/score?" +
    new URLSearchParams({ address: "700 W Grand Ave, Chicago, IL" }),
  { headers: { "X-API-Key": "lre_your_key_here" } }
);
const data = await res.json();
console.log(\`Livability: \${data.livability_score}/100\`);`}</pre>
        </section>

        {/* ── Rate Limits ─────────────────────────────────────────── */}
        <section id="rates" className="docs-section">
          <h2>Rate Limits</h2>
          <table className="docs-table">
            <thead><tr><th>Plan</th><th>Lookups / month</th><th>Bulk CSV</th><th>API access</th></tr></thead>
            <tbody>
              <tr><td>Free</td><td>10</td><td>&mdash;</td><td>Unauthenticated only</td></tr>
              <tr><td>Pro ($49/mo)</td><td>Unlimited</td><td>&mdash;</td><td>&mdash;</td></tr>
              <tr><td>Teams ($199/mo)</td><td>Unlimited</td><td>500 addresses</td><td>Full REST API</td></tr>
              <tr><td>Enterprise ($999+/mo)</td><td>Unlimited</td><td>10,000+</td><td>Full REST API + Webhooks</td></tr>
            </tbody>
          </table>
          <p className="docs-note">
            Rate limits are tracked per API key. Exceeding your plan&rsquo;s limits returns HTTP 429.
            <a href="/pricing"> Upgrade your plan</a> for higher limits.
          </p>
        </section>

        {/* ── Live Tester ─────────────────────────────────────────── */}
        <section id="tester" className="docs-section">
          <h2>Live API Tester</h2>
          <p>Enter an address below to see the raw JSON response from the <code>/score</code> endpoint.</p>
          <ApiTester />
        </section>

        {/* ── Coverage ────────────────────────────────────────────── */}
        <section id="coverage" className="docs-section">
          <h2>Coverage</h2>
          <p>
            Livability scores are available for addresses in 50+ US cities. Construction permits,
            street closures, and crime trend data coverage varies by city.
          </p>
          <div className="docs-city-grid">
            {[
              "Chicago", "New York", "Los Angeles", "Houston", "Dallas", "Phoenix",
              "Philadelphia", "San Antonio", "San Diego", "Austin", "San Francisco",
              "Seattle", "Denver", "Nashville", "Baltimore", "Portland", "Charlotte",
              "Columbus", "Minneapolis", "San Jose", "Fort Worth", "Indianapolis",
              "Jacksonville", "Memphis", "Louisville", "Milwaukee", "Albuquerque",
              "Tucson", "Fresno", "Sacramento", "Kansas City", "Atlanta",
              "New Orleans", "Cleveland", "Cincinnati", "Raleigh", "Oakland",
              "Tampa", "Miami", "Buffalo", "Pittsburgh", "Omaha",
              "Oklahoma City", "Baton Rouge", "El Paso", "Las Vegas",
              "Greensboro", "Richmond", "Lincoln", "Honolulu",
            ].map((city) => (
              <span key={city} className="docs-city-pill">{city}</span>
            ))}
          </div>
          <p className="docs-note">
            New cities are added regularly. Crime trend and school rating coverage
            is expanding &mdash; check the score response <code>mode</code> field
            to determine data availability for a specific address.
          </p>
        </section>
      </main>
    </div>
  );
}
