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
  { id: "bulk-csv", label: "Bulk CSV" },
  { id: "response", label: "Response Fields" },
  { id: "examples", label: "Code Examples" },
  { id: "access", label: "Pilot Access" },
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
        <h1 className="docs-title">Livability Risk Engine API</h1>
        <p className="docs-intro">
          Score addresses for near-term construction disruption using available public building
          permit and planned closure records. Returns a 0&ndash;100 livability score,
          backward-compatible disruption subscore, severity breakdown, evidence quality, and top risks.
        </p>

        {/* ── Authentication ─────────────────────────────────────── */}
        <section id="auth" className="docs-section">
          <h2>Authentication</h2>
          <p>
            Public single-address scoring is available through the website and public
            <code> /score</code> endpoint for evaluation. Technical API access for
            higher-volume, batch, export, or partner workflows is provisioned by request.
            Raw API integrations authenticate with an <code>X-API-Key</code> header.
            Do not put API keys in browser-facing forms or query parameters.
          </p>
          <pre className="docs-code">{`curl -s -X POST \\
  "https://livability-risk-engine-production.up.railway.app/score/batch" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: lre_your_key_here" \\
  --data '{"addresses":["1600 W Chicago Ave, Chicago, IL","350 5th Ave, New York, NY"]}'`}</pre>
          <p className="docs-note">
            API keys are issued by request for design partners and controlled pilots.
            Usage is currently reviewed operationally for design partners. Website Bulk CSV
            upload uses signed-in pilot account access rather than browser-entered keys.
          </p>
        </section>

        {/* ── Endpoint Reference ──────────────────────────────────── */}
        <section id="endpoint" className="docs-section">
          <h2>Endpoint Reference</h2>
          <div className="docs-endpoint-block">
            <span className="docs-method">GET</span>
            <code>/score?address=&#123;address&#125;</code>
          </div>
          <p>
            Public evaluation calls to <code>/score</code> accept a single full U.S. street
            address with city and state. Coverage and evidence depth vary by city and data type.
          </p>
          <h3>Parameters</h3>
          <table className="docs-table">
            <thead><tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
            <tbody>
              <tr><td><code>address</code></td><td>string</td><td>Yes</td><td>Full street address including city and state</td></tr>
            </tbody>
          </table>

          <h3>Sample Response</h3>
          <pre className="docs-code">{`{
  "address": "1600 W Chicago Ave, Chicago, IL",
  "livability_score": 48,
  "disruption_score": 62,
  "confidence": "MEDIUM",
  "severity": {
    "noise": "LOW",
    "traffic": "HIGH",
    "dust": "LOW"
  },
  "top_risks": [
    "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
    "Active closure window runs through the next 14 days",
    "Traffic and curb access are the dominant near-term disruption signals at this address"
  ],
  "explanation": "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic and curb access disruption even though noise and dust are limited.",
  "mode": "live",
  "evidence_quality": "moderate",
  "confidence_reason": "Specific nearby closure and permit signals are available, but coverage varies by source.",
  "latitude": 41.8956,
  "longitude": -87.6606,
  "nearby_signals": [ ... ],
  "livability_breakdown": {
    "components": {
      "disruption_risk": { "raw_score": 38, "weighted_contribution": 13.3 }
    }
  }
}`}</pre>
        </section>

        {/* ── Bulk CSV ───────────────────────────────────────────── */}
        <section id="bulk-csv" className="docs-section">
          <h2>Bulk CSV Scoring</h2>
          <p>
            Bulk CSV scoring is available in two pilot paths. Technical integrations can call
            the raw endpoint with an API key. Website users should use the signed-in
            <a href="/bulk"> Bulk CSV upload page</a>, which does not ask them to enter a key.
          </p>
          <div className="docs-endpoint-block">
            <span className="docs-method">POST</span>
            <code>/score/batch/csv</code>
          </div>
          <p>
            The request is <code>multipart/form-data</code> with the CSV in the
            <code> file</code> field and the pilot key in <code>X-API-Key</code>.
            Recommended columns are <code>street_address</code>, <code>city</code>,
            <code> state</code>, and optional <code>zip</code>. A single
            <code> address</code> column is also accepted. ZIP is optional but helpful,
            and two-letter state codes work best.
          </p>
          <pre className="docs-code">{`property_id,street_address,city,state,zip
demo-1,1600 W Chicago Ave,Chicago,IL,60622
demo-2,350 5th Ave,New York,NY,10118`}</pre>
          <p>
            The result CSV preserves original input columns where feasible, then appends
            <code> resolved_address</code>, score fields, evidence quality, severity,
            top risks, and row-level errors.
          </p>
          <pre className="docs-code">{`curl -s -X POST \\
  -H "X-API-Key: lre_your_key_here" \\
  -F "file=@addresses.csv" \\
  "https://livability-risk-engine-production.up.railway.app/score/batch/csv" \\
  -o livability_scores.csv`}</pre>
          <p className="docs-note">
            Prefer the <a href="/bulk">Bulk CSV upload page</a> for signed-in pilot users who
            want to upload a file and download results without writing code. The website route
            checks account access and keeps server credentials server-side.
          </p>
        </section>

        {/* ── Response Fields ─────────────────────────────────────── */}
        <section id="response" className="docs-section">
          <h2>Response Fields</h2>
          <table className="docs-table">
            <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
            <tbody>
              <tr><td><code>address</code></td><td>string</td><td>The geocoded address</td></tr>
              <tr><td><code>livability_score</code></td><td>integer</td><td>Public headline score, 0&ndash;100 where higher means better address livability and lower near-term risk</td></tr>
              <tr><td><code>disruption_score</code></td><td>integer</td><td>Backward-compatible disruption/risk subscore, 0&ndash;100 where higher means more near-term disruption risk</td></tr>
              <tr><td><code>confidence</code></td><td>string</td><td>LOW, MEDIUM, or HIGH &mdash; evidence trust and specificity, not severity or score direction</td></tr>
              <tr><td><code>evidence_quality</code></td><td>string</td><td>User-facing coverage/evidence signal such as strong, moderate, contextual_only, or insufficient</td></tr>
              <tr><td><code>severity</code></td><td>object</td><td>Three-axis severity: <code>noise</code>, <code>traffic</code>, <code>dust</code> (each LOW/MEDIUM/HIGH)</td></tr>
              <tr><td><code>top_risks</code></td><td>string[]</td><td>Plain-English descriptions of the top disruption signals</td></tr>
              <tr><td><code>explanation</code></td><td>string</td><td>Summary paragraph explaining the score</td></tr>
              <tr><td><code>mode</code></td><td>string</td><td><code>live</code> or <code>demo</code>; use evidence_quality and confidence_reason for coverage quality</td></tr>
              <tr><td><code>latitude</code>, <code>longitude</code></td><td>number</td><td>Geocoded coordinates</td></tr>
              <tr><td><code>nearby_signals</code></td><td>array</td><td>Active permits and closures within scoring radius</td></tr>
              <tr><td><code>livability_breakdown</code></td><td>object</td><td>Component scores; the disruption_risk component is inverted from disruption_score before contributing to livability</td></tr>
            </tbody>
          </table>
        </section>

        {/* ── Code Examples ───────────────────────────────────────── */}
        <section id="examples" className="docs-section">
          <h2>Code Examples</h2>

          <h3>Public /score evaluation</h3>
          <pre className="docs-code">{`curl -sG "https://livability-risk-engine-production.up.railway.app/score" \\
  --data-urlencode "address=700 W Grand Ave, Chicago, IL" \\
  | python3 -m json.tool`}</pre>

          <h3>Python partner integration</h3>
          <pre className="docs-code">{`import os
import requests

resp = requests.post(
    "https://livability-risk-engine-production.up.railway.app/score/batch",
    json={"addresses": ["700 W Grand Ave, Chicago, IL", "350 5th Ave, New York, NY"]},
    headers={"X-API-Key": os.environ["LRE_API_KEY"]},
)
data = resp.json()
print(f"Scored: {data['scored']}")
print(f"Failed: {data['failed']}")`}</pre>

          <h3>Server-side JavaScript partner integration</h3>
          <pre className="docs-code">{`const res = await fetch(
  "https://livability-risk-engine-production.up.railway.app/score/batch",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.LRE_API_KEY,
    },
    body: JSON.stringify({
      addresses: ["700 W Grand Ave, Chicago, IL", "350 5th Ave, New York, NY"],
    }),
  }
);
const data = await res.json();
console.log(\`Scored: \${data.scored}\`);`}</pre>
        </section>

        {/* ── Pilot Access ────────────────────────────────────────── */}
        <section id="access" className="docs-section">
          <h2>Pilot Access</h2>
          <table className="docs-table">
            <thead><tr><th>Capability</th><th>Current status</th><th>Notes</th></tr></thead>
            <tbody>
              <tr><td>Single-address demo</td><td>Available on the public app</td><td>Coverage varies by city and source.</td></tr>
              <tr><td>API / data partner access</td><td>Reviewed by request</td><td>Used for technical integrations and authenticated endpoints.</td></tr>
              <tr><td>Batch scoring and exports</td><td>Provisioned during pilot onboarding</td><td>Scopes and limits are set case-by-case.</td></tr>
              <tr><td>Bulk CSV upload</td><td>Available to signed-in pilot accounts</td><td><a href="/bulk">Upload CSV</a> and download scored results without entering a key in the browser.</td></tr>
            </tbody>
          </table>
          <p className="docs-note">
            During the design-partner pilot, API limits and access scopes are provisioned
            case-by-case. Contact the operator to request API access for batch scoring,
            exports, or integration use cases.
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
            The product provides address-level livability and disruption intelligence for U.S.
            properties. Coverage varies by city and data type. Chicago has the deepest permit
            and closure coverage; other metros may combine permit, closure, crime, flood,
            census, HPI, and neighborhood context data depending on source availability.
          </p>
          <div className="docs-city-grid">
            {[
              "City permit records",
              "Planned closure records",
              "Address-level score response",
            ].map((city) => (
              <span key={city} className="docs-city-pill">{city}</span>
            ))}
          </div>
          <p className="docs-note">
            Check <code>evidence_quality</code>, <code>confidence</code>, and
            <code> confidence_reason</code> before relying on a specific address result.
          </p>
        </section>
      </main>
    </div>
  );
}
