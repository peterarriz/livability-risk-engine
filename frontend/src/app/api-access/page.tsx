"use client";

// data-028: Developer portal — /api-access
// Fetches /docs/api-access from the backend and renders endpoint table, code tabs, auth section.

import React, { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Param = {
  name: string;
  in: string;
  required: boolean;
  type: string;
  description: string;
};

type ResponseField = {
  name: string;
  type: string;
  description: string;
};

type Endpoint = {
  id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  params: Param[];
  response_fields: ResponseField[];
  examples: { curl: string; python: string; javascript: string };
  example_response: unknown;
};

type ApiDocs = {
  title: string;
  version: string;
  description: string;
  base_url: string;
  auth: { type: string; note: string };
  endpoints: Endpoint[];
};

type CodeTab = "curl" | "python" | "javascript";

const TAB_LABELS: Record<CodeTab, string> = {
  curl: "curl",
  python: "Python",
  javascript: "JavaScript",
};

function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <div className="apidoc-code-block">
      <button className="apidoc-copy-btn" type="button" onClick={handleCopy} aria-label="Copy code">
        {copied ? "Copied" : "Copy"}
      </button>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function EndpointCard({ ep }: { ep: Endpoint }) {
  const [activeTab, setActiveTab] = useState<CodeTab>("curl");
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="apidoc-endpoint-card" id={`endpoint-${ep.id}`}>
      <button
        className="apidoc-endpoint-header"
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className={`apidoc-method apidoc-method--${ep.method.toLowerCase()}`}>{ep.method}</span>
        <span className="apidoc-path">{ep.path}</span>
        <span className="apidoc-summary">{ep.summary}</span>
        <span className="apidoc-chevron">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="apidoc-endpoint-body">
          <p className="apidoc-description">{ep.description}</p>

          {ep.params.length > 0 && (
            <div className="apidoc-section">
              <h4>Parameters</h4>
              <table className="apidoc-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>In</th>
                    <th>Required</th>
                    <th>Type</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {ep.params.map((p) => (
                    <tr key={p.name}>
                      <td><code>{p.name}</code></td>
                      <td>{p.in}</td>
                      <td>{p.required ? "Yes" : "No"}</td>
                      <td><code>{p.type}</code></td>
                      <td>{p.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="apidoc-section">
            <h4>Response fields</h4>
            <table className="apidoc-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Type</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {ep.response_fields.map((f) => (
                  <tr key={f.name}>
                    <td><code>{f.name}</code></td>
                    <td><code>{f.type}</code></td>
                    <td>{f.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="apidoc-section">
            <h4>Code examples</h4>
            <div className="apidoc-tabs" role="tablist">
              {(Object.keys(TAB_LABELS) as CodeTab[]).map((tab) => (
                <button
                  key={tab}
                  role="tab"
                  type="button"
                  className={`apidoc-tab${activeTab === tab ? " apidoc-tab--active" : ""}`}
                  onClick={() => setActiveTab(tab)}
                  aria-selected={activeTab === tab}
                >
                  {TAB_LABELS[tab]}
                </button>
              ))}
            </div>
            <CodeBlock code={ep.examples[activeTab]} />
          </div>

          <div className="apidoc-section">
            <h4>Example response</h4>
            <CodeBlock code={JSON.stringify(ep.example_response, null, 2)} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function ApiAccessPage() {
  const [docs, setDocs] = useState<ApiDocs | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/docs/api-access`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ApiDocs) => setDocs(data))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(`Could not load API docs (${msg}). Is the backend running?`);
      });
  }, []);

  return (
    <div className="apidoc-page">
      <header className="apidoc-page-header">
        <div className="apidoc-page-header-inner">
          <a href="/" className="apidoc-back-link">← Livability Risk Engine</a>
          <h1>Developer API</h1>
        </div>
      </header>

      <main className="apidoc-main">
        {error && (
          <div className="apidoc-error" role="alert">
            {error}
          </div>
        )}

        {!docs && !error && (
          <div className="apidoc-loading" aria-live="polite">
            Loading API documentation…
          </div>
        )}

        {docs && (
          <>
            <section className="apidoc-overview">
              <p className="apidoc-overview-desc">{docs.description}</p>
              <div className="apidoc-overview-meta">
                <span><strong>Version:</strong> {docs.version}</span>
                <span><strong>Base URL:</strong> <code>{docs.base_url}</code></span>
              </div>
            </section>

            <section className="apidoc-auth-section">
              <h2>Authentication</h2>
              <div className="apidoc-auth-badge">No API key required</div>
              <p>{docs.auth.note}</p>
            </section>

            <section className="apidoc-endpoints-section">
              <h2>Endpoints</h2>
              <div className="apidoc-endpoint-index">
                {docs.endpoints.map((ep) => (
                  <a key={ep.id} href={`#endpoint-${ep.id}`} className="apidoc-index-link">
                    <span className={`apidoc-method apidoc-method--${ep.method.toLowerCase()} apidoc-method--sm`}>
                      {ep.method}
                    </span>
                    {ep.path}
                  </a>
                ))}
              </div>
              <div className="apidoc-endpoint-list">
                {docs.endpoints.map((ep) => (
                  <EndpointCard key={ep.id} ep={ep} />
                ))}
              </div>
            </section>
          </>
        )}
      </main>

      <style>{`
        .apidoc-page {
          font-family: system-ui, -apple-system, sans-serif;
          background: #0a0a0a;
          color: #e5e5e5;
          min-height: 100vh;
        }
        .apidoc-page-header {
          border-bottom: 1px solid #222;
          padding: 1rem 0;
        }
        .apidoc-page-header-inner {
          max-width: 860px;
          margin: 0 auto;
          padding: 0 1.5rem;
          display: flex;
          align-items: center;
          gap: 1.5rem;
        }
        .apidoc-page-header h1 {
          margin: 0;
          font-size: 1.25rem;
          font-weight: 600;
          color: #fff;
        }
        .apidoc-back-link {
          color: #888;
          text-decoration: none;
          font-size: 0.875rem;
        }
        .apidoc-back-link:hover { color: #ccc; }
        .apidoc-main {
          max-width: 860px;
          margin: 0 auto;
          padding: 2rem 1.5rem 4rem;
        }
        .apidoc-loading, .apidoc-error {
          padding: 1rem;
          border-radius: 6px;
          font-size: 0.9rem;
        }
        .apidoc-loading { color: #888; }
        .apidoc-error { background: #1c0a0a; color: #f87171; border: 1px solid #7f1d1d; }
        .apidoc-overview { margin-bottom: 2rem; }
        .apidoc-overview-desc { color: #aaa; line-height: 1.6; margin: 0 0 0.75rem; }
        .apidoc-overview-meta { display: flex; gap: 2rem; font-size: 0.875rem; color: #888; flex-wrap: wrap; }
        .apidoc-overview-meta code { background: #1a1a1a; padding: 0.1em 0.4em; border-radius: 3px; font-size: 0.85em; }
        .apidoc-auth-section { margin-bottom: 2.5rem; }
        .apidoc-auth-section h2 { font-size: 1rem; font-weight: 600; color: #fff; margin: 0 0 0.5rem; }
        .apidoc-auth-badge {
          display: inline-block;
          background: #052e16;
          color: #4ade80;
          border: 1px solid #166534;
          border-radius: 4px;
          padding: 0.2em 0.6em;
          font-size: 0.8rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
        }
        .apidoc-auth-section p { color: #888; font-size: 0.875rem; margin: 0; }
        .apidoc-endpoints-section h2 { font-size: 1rem; font-weight: 600; color: #fff; margin: 0 0 0.75rem; }
        .apidoc-endpoint-index {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          margin-bottom: 1.5rem;
          background: #111;
          border: 1px solid #222;
          border-radius: 6px;
          padding: 0.75rem 1rem;
        }
        .apidoc-index-link {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          color: #aaa;
          text-decoration: none;
          font-size: 0.875rem;
          font-family: monospace;
        }
        .apidoc-index-link:hover { color: #fff; }
        .apidoc-endpoint-list { display: flex; flex-direction: column; gap: 0.75rem; }
        .apidoc-endpoint-card { border: 1px solid #222; border-radius: 8px; overflow: hidden; }
        .apidoc-endpoint-header {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          background: #111;
          border: none;
          cursor: pointer;
          color: #e5e5e5;
          text-align: left;
        }
        .apidoc-endpoint-header:hover { background: #161616; }
        .apidoc-path { font-family: monospace; font-size: 0.9rem; }
        .apidoc-summary { color: #888; font-size: 0.875rem; flex: 1; }
        .apidoc-chevron { color: #555; font-size: 0.75rem; margin-left: auto; }
        .apidoc-method {
          font-size: 0.7rem;
          font-weight: 700;
          font-family: monospace;
          padding: 0.15em 0.5em;
          border-radius: 3px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .apidoc-method--sm { font-size: 0.65rem; padding: 0.1em 0.4em; }
        .apidoc-method--get { background: #052e16; color: #4ade80; }
        .apidoc-method--post { background: #1e3a5f; color: #60a5fa; }
        .apidoc-endpoint-body {
          padding: 1.25rem;
          border-top: 1px solid #222;
          background: #0d0d0d;
        }
        .apidoc-description { color: #aaa; font-size: 0.875rem; line-height: 1.6; margin: 0 0 1.25rem; }
        .apidoc-section { margin-bottom: 1.5rem; }
        .apidoc-section h4 { font-size: 0.8rem; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 0.5rem; }
        .apidoc-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
        .apidoc-table th { text-align: left; padding: 0.4rem 0.5rem; color: #555; font-weight: 500; border-bottom: 1px solid #1e1e1e; }
        .apidoc-table td { padding: 0.4rem 0.5rem; color: #aaa; border-bottom: 1px solid #141414; vertical-align: top; }
        .apidoc-table code { background: #1a1a1a; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.85em; color: #e5e5e5; }
        .apidoc-tabs { display: flex; gap: 0; margin-bottom: 0; border-bottom: 1px solid #222; }
        .apidoc-tab {
          padding: 0.4rem 0.9rem;
          font-size: 0.8rem;
          background: none;
          border: none;
          border-bottom: 2px solid transparent;
          color: #666;
          cursor: pointer;
          margin-bottom: -1px;
        }
        .apidoc-tab:hover { color: #aaa; }
        .apidoc-tab--active { color: #fff; border-bottom-color: #3b82f6; }
        .apidoc-code-block {
          position: relative;
          background: #0f0f0f;
          border: 1px solid #1e1e1e;
          border-top: none;
          border-radius: 0 0 6px 6px;
          overflow: auto;
        }
        .apidoc-code-block pre {
          margin: 0;
          padding: 1rem;
          font-size: 0.78rem;
          line-height: 1.6;
          color: #ccc;
          overflow-x: auto;
          white-space: pre;
        }
        .apidoc-code-block code { font-family: "SF Mono", "Fira Code", monospace; }
        .apidoc-copy-btn {
          position: absolute;
          top: 0.5rem;
          right: 0.5rem;
          background: #1e1e1e;
          border: 1px solid #333;
          color: #888;
          border-radius: 4px;
          padding: 0.15rem 0.5rem;
          font-size: 0.7rem;
          cursor: pointer;
          z-index: 1;
        }
        .apidoc-copy-btn:hover { background: #2a2a2a; color: #ccc; }
      `}</style>
    </div>
  );
}
