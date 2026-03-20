"use client";

// data-021: Shareable report page
// Fetches a saved score result by UUID from the backend and renders it.
// URL: /report/<report_id>

import React, { useEffect, useState } from "react";
import {
  ExplanationPanel,
  getMeaningInsights,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { MapView } from "@/components/map-view";
import { Card, Container, Section } from "@/components/shell";
import { fetchReport, FetchReportResponse, ApiError, getExportUrl } from "@/lib/api";

export default function ReportPage({ params }: { params: { id: string } }) {
  const [report, setReport] = useState<FetchReportResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchReport(params.id)
      .then((data) => {
        if (!data) {
          setNotFound(true);
        } else {
          setReport(data);
        }
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError) {
          setError(err.message);
        } else {
          setError("Could not load this report.");
        }
      });
  }, [params.id]);

  function handleCopyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (errorMessage || !report) {
    return (
      <main style={{ maxWidth: "640px", margin: "4rem auto", padding: "0 1.5rem" }}>
        <p style={{ color: "#888", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
          Livability Risk Engine
        </p>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "1rem" }}>
          Report not found
        </h1>
        <p style={{ color: "#555" }}>
          {errorMessage ?? "This report may have expired or the link may be incorrect."}
        </p>
        <a
          href="/"
          style={{
            display: "inline-block",
            marginTop: "1.5rem",
            color: "#2563eb",
            textDecoration: "underline",
          }}
        >
          Run a new lookup →
        </a>
      </main>
    );
  }

  const savedDate = new Date(report.created_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <main style={{ maxWidth: "640px", margin: "4rem auto", padding: "0 1.5rem" }}>
      <p style={{ color: "#888", fontSize: "0.85rem", marginBottom: "0.25rem" }}>
        Livability Risk Engine — Saved Report
      </p>
      <p style={{ color: "#aaa", fontSize: "0.8rem", marginBottom: "2rem" }}>
        Saved on {savedDate}
      </p>

      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.5rem" }}>
        {report.address}
      </h1>

      <ScoreDisplay score={report.disruption_score} />

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Confidence &amp; Severity
        </h2>
        <p style={{ marginBottom: "0.5rem" }}>
          Confidence: <strong>{report.confidence}</strong>
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {Object.entries(report.severity).map(([key, val]) => (
            <span key={key} style={{ fontSize: "0.85rem" }}>
              {key.charAt(0).toUpperCase() + key.slice(1)}:{" "}
              <SeverityBadge level={val as string} />
            </span>
          ))}
        </div>
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Top Risk Signals
        </h2>
        <ul style={{ paddingLeft: "1.25rem", color: "#333" }}>
          {report.top_risks.map((risk, i) => (
            <li key={i} style={{ marginBottom: "0.4rem" }}>
              {risk}
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginBottom: "2rem" }}>
        <h2 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
          Interpretation
        </h2>
        <p style={{ color: "#333", lineHeight: 1.6 }}>{report.explanation}</p>
      </section>

      {report.mode === "demo" && (
        <p
          style={{
            background: "#fef9c3",
            border: "1px solid #fde047",
            borderRadius: "6px",
            padding: "0.75rem 1rem",
            fontSize: "0.85rem",
            color: "#713f12",
            marginBottom: "1.5rem",
          }}
        >
          This report was saved from a demo score. Live scoring requires a configured database.
        </p>
      )}

        {!report && !notFound && !error && (
          <Section eyebrow="Loading" title="Fetching saved report…">
            <Card className="empty-state">
              <p className="empty-kicker">Please wait</p>
              <h3>Loading disruption brief…</h3>
            </Card>
          </Section>
        )}

        {notFound && (
          <Section eyebrow="Not found" title="Report not found">
            <Card className="empty-state">
              <p className="empty-kicker">404</p>
              <h3>This report doesn&apos;t exist or has been removed.</h3>
              <p><a href="/">Score a new address →</a></p>
            </Card>
          </Section>
        )}

        {error && (
          <Section eyebrow="Error" title="Could not load report">
            <Card className="empty-state">
              <p className="empty-kicker">Error</p>
              <h3>{error}</h3>
              <p><a href="/">Score a new address →</a></p>
            </Card>
          </Section>
        )}

        {score && (
          <>
            <Section
              eyebrow="Saved disruption brief"
              title={score.address}
              description={
                report?.created_at
                  ? `Saved on ${new Date(report.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`
                  : "Saved report"
              }
            >
              <div className="report-actions">
                <button type="button" className="action-btn" onClick={handleCopyLink}>
                  {copied ? "Link copied!" : "Copy shareable link"}
                </button>
                <a
                  href={getExportUrl("csv", score.address)}
                  className="action-btn"
                  title="Download score as CSV"
                >
                  ↓ CSV
                </a>
                <a
                  href={getExportUrl("pdf", score.address)}
                  target="_blank"
                  rel="noreferrer"
                  className="action-btn"
                  title="Open print-ready PDF"
                >
                  ↓ PDF
                </a>
                <a href="/" className="compare-link">Score another address →</a>
              </div>

              <div className="workspace-top-grid">
                <Card className="score-card">
                  <ScoreHero result={score} />
                </Card>
                <Card className="detail-card detail-card--summary">
                  <h2>Why this score</h2>
                  <ExplanationPanel explanation={score.explanation} meaning={meaningInsights} />
                </Card>
              </div>

              <div className="detail-grid detail-grid--balanced">
                <Card className="detail-card">
                  <h2>Confidence and severity</h2>
                  <SeverityMeters
                    severity={score.severity}
                    confidence={score.confidence}
                    confidenceReasons={[]}
                  />
                </Card>
                <Card className="detail-card supporting-card">
                  <p className="supporting-kicker">Quick read</p>
                  <ul className="supporting-list supporting-list--compact">
                    <li>
                      <span>Data mode</span>
                      <strong>{score.mode === "demo" ? "Demo fallback" : "Live Chicago feed"}</strong>
                    </li>
                    <li>
                      <span>Confidence</span>
                      <strong>
                        <span className={`confidence-dot confidence-dot--${score.confidence.toLowerCase()}`} aria-hidden="true" />
                        {score.confidence}
                      </strong>
                    </li>
                    <li>
                      <span>Active signals detected</span>
                      <strong>{score.top_risks.length}</strong>
                    </li>
                    <li>
                      <span>Sources</span>
                      <strong>Chicago permits · Street closures</strong>
                    </li>
                  </ul>
                </Card>
              </div>

              <Section
                eyebrow="Signals"
                title="Strongest supporting drivers"
                description="The clearest nearby signals behind this score."
                className="workspace-subsection"
              >
                <Card className="detail-card drivers-card">
                  <TopRiskGrid result={score} />
                </Card>
              </Section>

              {mapCoords && (
                <Card className="detail-card map-card">
                  <div className="map-card-head">
                    <div>
                      <p className="map-kicker">Spatial context</p>
                      <h2>Address and nearby area</h2>
                    </div>
                    <span className="map-badge">OpenStreetMap</span>
                  </div>
                  <MapView latitude={mapCoords.lat} longitude={mapCoords.lon} address={score.address} />
                  <p className="map-copy">Use the map to anchor the score geographically.</p>
                </Card>
              )}
            </Section>
          </>
        )}
      </Container>
    </main>
  );
}
