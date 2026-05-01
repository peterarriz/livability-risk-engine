"use client";

// data-028: Developer portal page
// URL: /api-access
// Fetches live docs from GET /docs/api-access and renders endpoint table,
// auth instructions, and copy-paste code examples.

import React, { useEffect, useState } from "react";
import { Card, Container, Section } from "@/components/shell";

type EndpointDoc = { method: string; path: string; description: string };

type ApiAccessDoc = {
  title: string;
  version: string;
  description: string;
  auth: { required: boolean; method: string; request_access: string };
  endpoints: EndpointDoc[];
  rate_limits: string;
  example: {
    request: string;
    response_shape: Record<string, unknown>;
  };
};

const METHOD_COLORS: Record<string, string> = {
  GET: "method-get",
  POST: "method-post",
  DELETE: "method-delete",
};

type CodeTab = "curl" | "python" | "javascript";

const CODE_EXAMPLES: Record<CodeTab, string> = {
  curl: `# Score an address
curl "https://your-api.railway.app/score?address=1600+W+Chicago+Ave+Chicago+IL" \\
  -H "X-API-Key: YOUR_API_KEY"

# Address autocomplete
curl "https://your-api.railway.app/suggest?q=chicago+ave" \\
  -H "X-API-Key: YOUR_API_KEY"

# Score history
curl "https://your-api.railway.app/history?address=1600+W+Chicago+Ave+Chicago+IL&limit=10" \\
  -H "X-API-Key: YOUR_API_KEY"`,

  python: `import requests

BASE = "https://your-api.railway.app"
HEADERS = {"X-API-Key": "YOUR_API_KEY"}

# Score an address
resp = requests.get(
    f"{BASE}/score",
    params={"address": "1600 W Chicago Ave Chicago IL"},
    headers=HEADERS,
)
data = resp.json()
print(f"Livability Score: {data['livability_score']} / 100")
print(f"Disruption Score: {data['disruption_score']} / 100")
print(f"Confidence: {data['confidence']}")
for risk in data["top_risks"]:
    print(f"  - {risk}")

# Score history for trend analysis
history = requests.get(
    f"{BASE}/history",
    params={"address": "1600 W Chicago Ave Chicago IL", "limit": 20},
    headers=HEADERS,
).json()
scores = [h.get("livability_score", h.get("disruption_score")) for h in history["history"]]
print(f"Historical scores: {scores}")`,

  javascript: `const BASE = "https://your-api.railway.app";
const KEY = "YOUR_API_KEY";
const headers = { "X-API-Key": KEY };

// Score an address
const score = await fetch(
  \`\${BASE}/score?address=\${encodeURIComponent("1600 W Chicago Ave Chicago IL")}\`,
  { headers }
).then(r => r.json());

console.log(\`Livability Score: \${score.livability_score} / 100\`);
console.log(\`Disruption Score: \${score.disruption_score} / 100\`);
console.log(\`Top risks:\`, score.top_risks);`,
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
  const [docs, setDocs] = useState<ApiAccessDoc | null>(null);
  const [activeTab, setActiveTab] = useState<CodeTab>("curl");
  const [copiedExample, setCopiedExample] = useState(false);
  const [copiedResponse, setCopiedResponse] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const enableLiveDocs = process.env.NEXT_PUBLIC_ENABLE_LIVE_API_DOCS === "1";

  useEffect(() => {
    if (!enableLiveDocs) return;
    fetch(`${apiBase}/docs/api-access`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setDocs(data))
      .catch(() => null);
  }, [apiBase, enableLiveDocs]);

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
          description="Programmatic access to the multi-city disruption score. Query one address and get the headline livability score, backward-compatible disruption subscore, severity dimensions, and evidence context."
        >
          {/* Auth box */}
          <Card className="detail-card api-auth-card">
            <div className="api-auth-head">
              <div>
                <p className="supporting-kicker">Authentication</p>
                <h2>{docs?.auth?.required ? "API key required" : "Demo access available"}</h2>
              </div>
              <span className={`api-auth-badge ${docs?.auth?.required ? "api-auth-badge--required" : "api-auth-badge--open"}`}>
                {docs?.auth?.required ? "Key required" : "Demo access"}
              </span>
            </div>
            <p className="api-auth-copy">
              {docs?.auth?.method ?? "Pass your API key in the X-API-Key header when key enforcement is enabled."}
            </p>
            <div className="api-auth-example">
              <code>X-API-Key: lre_xxxxxxxxxxxxxxxxxxxxxxxx</code>
            </div>
            <p className="modal-fine-print">{docs?.auth?.request_access ?? "Contact the operator to request an API key."}</p>
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
                {(docs?.endpoints ?? FALLBACK_ENDPOINTS).map((ep) => (
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
                <span>Rate limits</span>
                <strong>{docs?.rate_limits ?? "Public demo usage is limited; authenticated use is operator-managed."}</strong>
              </li>
              <li>
                <span>Coverage</span>
                <strong>Multi-city, coverage-aware scoring; evidence depth varies by city, source, and record availability.</strong>
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
  { method: "GET", path: "/score", description: "Score one address" },
  { method: "GET", path: "/suggest", description: "Address autocomplete" },
  { method: "GET", path: "/history", description: "Score history for an address" },
  { method: "POST", path: "/save", description: "Save a score result and get a shareable link" },
  { method: "GET", path: "/report/{report_id}", description: "Fetch a previously saved report" },
  { method: "GET", path: "/export/csv", description: "Download score as CSV" },
  { method: "GET", path: "/health", description: "Backend readiness check" },
];
