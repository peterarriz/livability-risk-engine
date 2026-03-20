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

  const score = report?.score ?? null;
  const meaningInsights = score ? getMeaningInsights(score) : [];
  const mapCoords =
    score?.latitude != null && score?.longitude != null
      ? { lat: score.latitude, lon: score.longitude }
      : null;

  return (
    <main>
      <Container>
        <div className="report-header">
          <a href="/" className="report-back-link">← Back to Livability Risk Engine</a>
        </div>

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
