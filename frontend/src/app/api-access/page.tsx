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
curl "https://your-api.railway.app/score?address=100+W+Randolph+St+Chicago+IL" \\
  -H "X-Api-Key: YOUR_API_KEY"

# Address autocomplete
curl "https://your-api.railway.app/suggest?q=michigan+ave" \\
  -H "X-Api-Key: YOUR_API_KEY"

# Score history
curl "https://your-api.railway.app/history?address=100+W+Randolph+St+Chicago+IL&limit=10" \\
  -H "X-Api-Key: YOUR_API_KEY"

# Neighborhood projects
curl "https://your-api.railway.app/neighborhood/west-loop" \\
  -H "X-Api-Key: YOUR_API_KEY"`,

  python: `import requests

BASE = "https://your-api.railway.app"
HEADERS = {"X-Api-Key": "YOUR_API_KEY"}

# Score an address
resp = requests.get(
    f"{BASE}/score",
    params={"address": "100 W Randolph St Chicago IL"},
    headers=HEADERS,
)
data = resp.json()
print(f"Score: {data['disruption_score']} / 100")
print(f"Confidence: {data['confidence']}")
for risk in data["top_risks"]:
    print(f"  - {risk}")

# Score history for trend analysis
history = requests.get(
    f"{BASE}/history",
    params={"address": "100 W Randolph St Chicago IL", "limit": 20},
    headers=HEADERS,
).json()
scores = [h["disruption_score"] for h in history["history"]]
print(f"Historical scores: {scores}")`,

  javascript: `const BASE = "https://your-api.railway.app";
const KEY = "YOUR_API_KEY";
const headers = { "X-Api-Key": KEY };

// Score an address
const score = await fetch(
  \`\${BASE}/score?address=\${encodeURIComponent("100 W Randolph St Chicago IL")}\`,
  { headers }
).then(r => r.json());

console.log(\`Score: \${score.disruption_score} / 100\`);
console.log(\`Top risks:\`, score.top_risks);

// Get neighborhood projects
const hood = await fetch(\`\${BASE}/neighborhood/west-loop\`, { headers })
  .then(r => r.json());

console.log(\`\${hood.name}: \${hood.projects.length} active projects\`);`,
};

const EXAMPLE_RESPONSE = JSON.stringify(
  {
    address: "100 W Randolph St Chicago IL",
    disruption_score: 47,
    confidence: "MEDIUM",
    severity: { noise: "LOW", traffic: "HIGH", dust: "LOW" },
    top_risks: [
      "Multi-lane closure on W Randolph St within roughly 85 meters; active through 2026-04-15",
      "Active construction permit near 120 W Randolph St within roughly 210 meters",
      "Lane or curb closure near N LaSalle St within roughly 320 meters",
    ],
    explanation: "A nearby lane closure is the main driver, giving this address elevated short-term traffic disruption.",
    mode: "live",
    fallback_reason: null,
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

  useEffect(() => {
    fetch(`${apiBase}/docs/api-access`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setDocs(data))
      .catch(() => null);
  }, [apiBase]);

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
          description="Programmatic access to Chicago disruption scoring. Query any Chicago address and get a structured risk score with severity breakdown and supporting signals."
        >
          {/* Auth box */}
          <Card className="detail-card api-auth-card">
            <div className="api-auth-head">
              <div>
                <p className="supporting-kicker">Authentication</p>
                <h2>{docs?.auth.required ? "API key required" : "No auth required (public)"}</h2>
              </div>
              <span className={`api-auth-badge ${docs?.auth.required ? "api-auth-badge--required" : "api-auth-badge--open"}`}>
                {docs?.auth.required ? "Key required" : "Open access"}
              </span>
            </div>
            <p className="api-auth-copy">
              {docs?.auth.method ?? "Pass your API key in the X-Api-Key header or as a ?api_key= query parameter."}
            </p>
            <div className="api-auth-example">
              <code>X-Api-Key: lre_xxxxxxxxxxxxxxxxxxxxxxxx</code>
            </div>
            <p className="modal-fine-print">{docs?.auth.request_access ?? "Contact the operator to request an API key."}</p>
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
                <strong>{docs?.rate_limits ?? "Unauthenticated requests are rate-limited at the infrastructure level."}</strong>
              </li>
              <li>
                <span>Coverage</span>
                <strong>Chicago, IL addresses only (MVP). City expansion roadmap: NYC, LA, Boston.</strong>
              </li>
              <li>
                <span>Data freshness</span>
                <strong>Ingest runs daily at 06:00 UTC from Chicago Open Data (permits + CDOT closures).</strong>
              </li>
              <li>
                <span>Score range</span>
                <strong>0–100. Bands: 0–24 Low · 25–49 Moderate · 50–74 High · 75–100 Severe.</strong>
              </li>
            </ul>
          </Card>
        </Section>
      </Container>
    </main>
  );
}

const FALLBACK_ENDPOINTS: EndpointDoc[] = [
  { method: "GET", path: "/score", description: "Score a Chicago address (0–100)" },
  { method: "GET", path: "/suggest", description: "Address autocomplete (Nominatim-backed)" },
  { method: "GET", path: "/history", description: "Score history for an address" },
  { method: "GET", path: "/neighborhood/{slug}", description: "Projects in a named Chicago neighborhood" },
  { method: "POST", path: "/save", description: "Save a score result and get a shareable link" },
  { method: "GET", path: "/report/{report_id}", description: "Fetch a previously saved report" },
  { method: "GET", path: "/export/csv", description: "Download score as CSV" },
  { method: "GET", path: "/health", description: "Backend readiness check" },
];
