"use client";

// data-021: Shareable report page
// Fetches a saved score result by UUID from the backend and renders it.
// URL: /report/<report_id>

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  ExplanationPanel,
  getConfidenceReasons,
  getMeaningInsights,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { MapView } from "@/components/map-view";
import { Card, Section } from "@/components/shell";
import { fetchReport, FetchReportResponse, ApiError, getExportUrl } from "@/lib/api";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const reportId = Array.isArray(params.id) ? params.id[0] : params.id;
  const [report, setReport] = useState<FetchReportResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [embedCopied, setEmbedCopied] = useState(false);

  useEffect(() => {
    fetchReport(reportId)
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
  }, [reportId]);

  function handleCopyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const meaningInsights = useMemo(
    () => (report ? getMeaningInsights(report) : []),
    [report],
  );

  const confidenceReasons = useMemo(
    () => (report ? getConfidenceReasons(report) : []),
    [report],
  );

  const mapCoords =
    report?.latitude != null && report?.longitude != null
      ? { lat: report.latitude, lon: report.longitude }
      : null;

  if (!report && !notFound && !error) {
    return (
      <div className="page">
        <div className="shell-container">
          <Section eyebrow="Loading" title="Fetching saved report…">
            <Card className="empty-state">
              <p className="empty-kicker">Please wait</p>
              <h3>Loading disruption brief…</h3>
            </Card>
          </Section>
        </div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="page">
        <div className="shell-container">
          <Section eyebrow="Not found" title="Report not found">
            <Card className="empty-state">
              <p className="empty-kicker">404</p>
              <h3>This report doesn&apos;t exist or has been removed.</h3>
              <p><a href="/">Score a new address →</a></p>
            </Card>
          </Section>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="shell-container">
          <Section eyebrow="Error" title="Could not load report">
            <Card className="empty-state">
              <p className="empty-kicker">Error</p>
              <h3>{error}</h3>
              <p><a href="/">Score a new address →</a></p>
            </Card>
          </Section>
        </div>
      </div>
    );
  }

  if (!report) return null;

  return (
    <div className="page">
      <div className="shell-container">
        <Section
          eyebrow="Saved disruption brief"
          title={report.address}
          description={
            report.created_at
              ? `Saved on ${new Date(report.created_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}`
              : "Saved report"
          }
        >
          <div className="score-actions" style={{ marginBottom: "1.5rem" }}>
            <button type="button" className="action-btn" onClick={handleCopyLink}>
              {copied ? "Link copied!" : "Copy shareable link"}
            </button>
            <a
              href={getExportUrl("csv", report.address)}
              className="action-btn"
              title="Download score as CSV"
            >
              ↓ CSV
            </a>
            <a
              href={getExportUrl("pdf", report.address)}
              target="_blank"
              rel="noreferrer"
              className="action-btn"
              title="Open print-ready PDF"
            >
              ↓ PDF
            </a>
            <button
              type="button"
              className="action-btn"
              onClick={() => {
                const code = `<iframe src="${window.location.origin}/widget/${params.id}" width="320" height="200" frameborder="0" style="border-radius:12px;border:1px solid rgba(0,0,0,0.1)"></iframe>`;
                navigator.clipboard.writeText(code).then(() => {
                  setEmbedCopied(true);
                  setTimeout(() => setEmbedCopied(false), 2500);
                });
              }}
            >
              {embedCopied ? "Embed code copied!" : "Embed widget"}
            </button>
            <a href="/" className="compare-link">Score another address →</a>
          </div>

          <p className="report-disclaimer">
            This report reflects the livability score at the time it was generated.
            Scores update live as new data becomes available &mdash;{" "}
            <a href={`/?address=${encodeURIComponent(report?.address ?? "")}`}>
              check the current score
            </a>.
          </p>

          <div className="workspace-top-grid">
            <Card className="score-card">
              <ScoreHero result={report} />
            </Card>
            <Card className="detail-card detail-card--summary">
              <h2>Why this score</h2>
              <ExplanationPanel explanation={report.explanation} meaning={meaningInsights} />
            </Card>
          </div>

          <div className="detail-grid detail-grid--balanced">
            <Card className="detail-card">
              <h2>Confidence and severity</h2>
              <SeverityMeters
                severity={report.severity}
                confidence={report.confidence}
                confidenceReasons={confidenceReasons}
              />
            </Card>
            <Card className="detail-card supporting-card">
              <p className="supporting-kicker">Quick read</p>
              <ul className="supporting-list supporting-list--compact">
                <li>
                  <span>Data mode</span>
                  <strong>{report.mode === "demo" ? "Demo fallback" : "Live Chicago feed"}</strong>
                </li>
                <li>
                  <span>Confidence</span>
                  <strong>
                    <span
                      className={`confidence-dot confidence-dot--${report.confidence.toLowerCase()}`}
                      aria-hidden="true"
                    />
                    {report.confidence}
                  </strong>
                </li>
                <li>
                  <span>Active signals detected</span>
                  <strong>{report.top_risks.length}</strong>
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
          >
            <Card className="detail-card drivers-card">
              <TopRiskGrid result={report} />
            </Card>
          </Section>

          {mapCoords && (
            <Card className="detail-card map-card">
              <div className="map-card-head">
                <div>
                  <p className="map-kicker">Spatial context</p>
                  <h2>Address and nearby area</h2>
                </div>
                <span className="map-badge">Stadia Dark</span>
              </div>
              <MapView
                latitude={mapCoords.lat}
                longitude={mapCoords.lon}
                address={report.address}
                disruptionScore={report.disruption_score}
                signals={report.nearby_signals ?? []}
                nearbySchools={report.nearby_schools ?? []}
              />
              <p className="map-copy">Use the map to anchor the score geographically.</p>
            </Card>
          )}
        </Section>
      </div>
    </div>
  );
}
