/**
 * frontend/src/app/report/[id]/page.tsx
 * task: data-021
 *
 * Shareable report page. Fetches a saved score result by UUID and renders it
 * in a read-only view so users can share /report/<uuid> with others.
 *
 * This is a Server Component — data is fetched at request time on the server.
 * No client-side interactivity is needed for a read-only report view.
 */

import { fetchReport, ReportResponse } from "@/lib/api";

type ReportPageProps = {
  params: { id: string };
};

function SeverityBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    HIGH: "#c0392b",
    MEDIUM: "#e67e22",
    LOW: "#27ae60",
  };
  const color = colors[level] ?? "#888";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "4px",
        background: color,
        color: "#fff",
        fontWeight: 600,
        fontSize: "0.75rem",
        letterSpacing: "0.05em",
      }}
    >
      {level}
    </span>
  );
}

function ScoreDisplay({ score }: { score: number }) {
  const color = score >= 70 ? "#c0392b" : score >= 40 ? "#e67e22" : "#27ae60";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.5rem",
        margin: "0.5rem 0 1rem",
      }}
    >
      <span
        style={{
          fontSize: "3rem",
          fontWeight: 800,
          color,
          lineHeight: 1,
        }}
      >
        {score}
      </span>
      <span style={{ color: "#666", fontSize: "0.9rem" }}>/100 disruption score</span>
    </div>
  );
}

export default async function ReportPage({ params }: ReportPageProps) {
  let report: ReportResponse | null = null;
  let errorMessage: string | null = null;

  try {
    report = await fetchReport(params.id);
  } catch (err) {
    errorMessage = err instanceof Error ? err.message : "Could not load report.";
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

      <a
        href="/"
        style={{ color: "#2563eb", textDecoration: "underline", fontSize: "0.9rem" }}
      >
        ← Run a new lookup
      </a>
    </main>
  );
}
