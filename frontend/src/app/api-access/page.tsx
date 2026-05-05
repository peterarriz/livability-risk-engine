"use client";

// data-028: Developer portal page
// URL: /api-access
// Renders endpoint table, auth instructions, and copy-paste code examples.

import React, { useState } from "react";
import { Card, Container, Section } from "@/components/shell";

type EndpointDoc = { method: string; path: string; description: string };

const METHOD_COLORS: Record<string, string> = {
  GET: "method-get",
  POST: "method-post",
  DELETE: "method-delete",
};

type CodeTab = "curl" | "python" | "javascript";

const PUBLIC_API_BASE = "https://livability-risk-engine-production.up.railway.app";

const CODE_EXAMPLES: Record<CodeTab, string> = {
  curl: `# Public single-address scoring
curl -sG "${PUBLIC_API_BASE}/score" \\
  --data-urlencode "address=1600 W Chicago Ave, Chicago, IL"

# Provisioned partner batch scoring
curl -s -X POST "${PUBLIC_API_BASE}/score/batch" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: lre_your_key_here" \\
  --data '{"addresses":["1600 W Chicago Ave, Chicago, IL","350 5th Ave, New York, NY"]}'`,

  python: `import os
import requests

BASE = "${PUBLIC_API_BASE}"

# Public single-address scoring
resp = requests.get(
    f"{BASE}/score",
    params={"address": "1600 W Chicago Ave, Chicago, IL"},
)
data = resp.json()
print(f"Livability Score: {data['livability_score']} / 100")
print(f"Disruption Score: {data['disruption_score']} / 100")
print(f"Confidence: {data['confidence']}")

# Provisioned partner batch scoring
batch = requests.post(
    f"{BASE}/score/batch",
    json={"addresses": ["1600 W Chicago Ave, Chicago, IL", "350 5th Ave, New York, NY"]},
    headers={"X-API-Key": os.environ["LRE_API_KEY"]},
).json()
print(f"Batch scored: {batch['scored']}")`,

  javascript: `const BASE = "${PUBLIC_API_BASE}";

// Public single-address scoring
const score = await fetch(
  \`\${BASE}/score?\${new URLSearchParams({
    address: "1600 W Chicago Ave, Chicago, IL",
  })}\`
).then(r => r.json());

console.log(\`Livability Score: \${score.livability_score} / 100\`);
console.log(\`Disruption Score: \${score.disruption_score} / 100\`);
console.log(\`Top risks:\`, score.top_risks);

// Server-side partner integrations can call protected batch endpoints.
const batch = await fetch(\`\${BASE}/score/batch\`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": process.env.LRE_API_KEY ?? "",
  },
  body: JSON.stringify({
    addresses: ["1600 W Chicago Ave, Chicago, IL", "350 5th Ave, New York, NY"],
  }),
}).then(r => r.json());

console.log(\`Batch scored: \${batch.scored}\`);`,
};

const EXAMPLE_RESPONSE = JSON.stringify(
  {
    address: "1600 W Chicago Ave, Chicago, IL",
    livability_score: 48,
    disruption_score: 62,
    confidence: "MEDIUM",
    evidence_quality: "moderate",
    severity: { noise: "LOW", traffic: "HIGH", dust: "LOW" },
    top_risks: [
      "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
      "Active closure window runs through the next 14 days",
      "Traffic and curb access are the dominant near-term disruption signals at this address",
    ],
    explanation: "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic and curb access disruption even though noise and dust are limited.",
    mode: "live",
    fallback_reason: null,
    confidence_reason: "Specific nearby closure signals are available; coverage depth varies by source.",
    livability_breakdown: {
      components: {
        disruption_risk: { raw_score: 38, weighted_contribution: 13.3 },
        crime_trend: { raw_score: 50, weighted_contribution: 12.5 },
        school_rating: { raw_score: 58, weighted_contribution: 11.6 },
      },
    },
  },
  null,
  2,
);

export default function ApiAccessPage() {
  const [activeTab, setActiveTab] = useState<CodeTab>("curl");
  const [copiedExample, setCopiedExample] = useState(false);
  const [copiedResponse, setCopiedResponse] = useState(false);

  function copyText(text: string, setter: (v: boolean) => void) {
    navigator.clipboard.writeText(text).then(() => {
      setter(true);
      setTimeout(() => setter(false), 2000);
    });
  }

  return (
    <main>
      <Container>
        <div className="report-header">
          <a href="/" className="report-back-link">← Back to Livability Risk Engine</a>
        </div>

        <Section
          eyebrow="Developer"
          title="API Reference"
          description="Programmatic access to address-level livability and disruption scoring for U.S. properties. API access is by request during the design-partner pilot."
        >
          {/* Auth box */}
          <Card className="detail-card api-auth-card">
            <div className="api-auth-head">
              <div>
                <p className="supporting-kicker">Authentication</p>
                <h2>Public demo and pilot API</h2>
              </div>
              <span className="api-auth-badge api-auth-badge--open">
                By request
              </span>
            </div>
            <p className="api-auth-copy">
              Public single-address scoring is available through the website and public
              <code> /score</code> endpoint for evaluation. Technical API access for
              higher-volume, batch, export, or partner workflows is provisioned by request.
              Raw API integrations use an <code>X-API-Key</code> header. Do not put API
              keys in browser-facing forms or query parameters.
            </p>
            <div className="api-auth-example">
              <code>X-API-Key: lre_xxxxxxxxxxxxxxxxxxxxxxxx</code>
            </div>
            <p className="modal-fine-print">Contact the operator to request API access during the pilot.</p>
          </Card>

          {/* Endpoints table */}
          <Card className="detail-card">
            <h2>Endpoints</h2>
            <table className="api-endpoints-table">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Path</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {FALLBACK_ENDPOINTS.map((ep) => (
                  <tr key={ep.path}>
                    <td>
                      <span className={`api-method-badge ${METHOD_COLORS[ep.method] ?? ""}`}>
                        {ep.method}
                      </span>
                    </td>
                    <td><code className="api-path">{ep.path}</code></td>
                    <td>{ep.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card className="detail-card supporting-card">
            <span id="pilot-bulk-access" />
            <p className="supporting-kicker">Pilot bulk workflow</p>
            <h2>Bulk CSV scoring</h2>
            <p className="api-auth-copy">
              Bulk CSV website upload is available to signed-in pilot and internal accounts.
              Raw technical CSV integrations use <code>X-API-Key</code>; browser users should
              upload through the website flow without entering credentials into the page.
            </p>
            <p className="modal-fine-print">
              Use the <a href="/bulk">Bulk CSV upload page</a> for signed-in pilot users.
              The request limit remains 200 addresses per upload.
            </p>
          </Card>

          {/* Code examples */}
          <Card className="detail-card">
            <div className="api-code-head">
              <h2>Code examples</h2>
              <div className="api-tab-row">
                {(["curl", "python", "javascript"] as CodeTab[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    className={`api-tab-btn${activeTab === tab ? " api-tab-btn--active" : ""}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab === "curl" ? "cURL" : tab === "python" ? "Python" : "JavaScript"}
                  </button>
                ))}
              </div>
            </div>
            <div className="api-code-block-wrapper">
              <pre className="api-code-block"><code>{CODE_EXAMPLES[activeTab]}</code></pre>
              <button
                type="button"
                className="api-copy-btn"
                onClick={() => copyText(CODE_EXAMPLES[activeTab], setCopiedExample)}
              >
                {copiedExample ? "Copied!" : "Copy"}
              </button>
            </div>
          </Card>

          {/* Example response */}
          <Card className="detail-card">
            <div className="api-code-head">
              <h2>Example response — <code>/score</code></h2>
            </div>
            <div className="api-code-block-wrapper">
              <pre className="api-code-block"><code>{EXAMPLE_RESPONSE}</code></pre>
              <button
                type="button"
                className="api-copy-btn"
                onClick={() => copyText(EXAMPLE_RESPONSE, setCopiedResponse)}
              >
                {copiedResponse ? "Copied!" : "Copy"}
              </button>
            </div>
          </Card>

          {/* Rate limits + notes */}
          <Card className="detail-card supporting-card">
            <p className="supporting-kicker">Usage notes</p>
            <ul className="supporting-list">
              <li>
                <span>Access and limits</span>
                <strong>Provisioned case-by-case during the design-partner pilot.</strong>
              </li>
              <li>
                <span>Coverage</span>
                <strong>Coverage varies by city and data type. Chicago has the deepest permit and closure coverage; other metros may combine permit, closure, crime, flood, census, HPI, and neighborhood context data depending on source availability.</strong>
              </li>
              <li>
                <span>Data freshness</span>
                <strong>Source refresh varies. Use evidence_quality, confidence, and confidence_reason before relying on a result.</strong>
              </li>
              <li>
                <span>Score range</span>
                <strong>Livability Score is 0–100, higher is better. Disruption Score is 0–100, higher means more near-term disruption risk.</strong>
              </li>
            </ul>
          </Card>
        </Section>
      </Container>
    </main>
  );
}

const FALLBACK_ENDPOINTS: EndpointDoc[] = [
  { method: "GET", path: "/score", description: "Public single-address score for a full U.S. street address" },
  { method: "GET", path: "/health", description: "Public liveness check" },
  { method: "GET", path: "/suggest", description: "Public address autocomplete" },
  { method: "GET", path: "/history", description: "Recent score history for an address" },
  { method: "POST", path: "/score/batch", description: "Protected batch scoring for provisioned API partners; requires X-API-Key" },
  { method: "POST", path: "/score/batch/csv", description: "Protected technical CSV scoring; requires X-API-Key" },
  { method: "GET", path: "/export/csv", description: "Protected score and signal export; requires X-API-Key" },
];
