"use client";

/**
 * /widget/[id] — Embeddable score widget for property listings.
 *
 * Renders a compact score card (320x200) suitable for iframe embedding.
 * Supports light and dark modes via ?theme=light|dark query parameter.
 * Links back to the full report at /report/[id].
 */

import { useEffect, useState } from "react";
import { fetchReport, FetchReportResponse } from "@/lib/api";
import { headlineScore } from "@/lib/score-utils";

function riskLevel(score: number): { label: string; color: string } {
  if (score >= 70) return { label: "Low Risk", color: "#10b981" };
  if (score >= 50) return { label: "Moderate Risk", color: "#f59e0b" };
  if (score >= 30) return { label: "High Risk", color: "#ef4444" };
  return { label: "Severe Risk", color: "#dc2626" };
}

export default function WidgetPage({ params }: { params: { id: string } }) {
  const [report, setReport] = useState<FetchReportResponse | null>(null);
  const [error, setError] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    // Read theme from URL
    const t = new URLSearchParams(window.location.search).get("theme");
    if (t === "light") setTheme("light");

    fetchReport(params.id)
      .then((data) => {
        if (!data) setError(true);
        else setReport(data);
      })
      .catch(() => setError(true));
  }, [params.id]);

  const isDark = theme === "dark";
  const bg = isDark ? "#0d1525" : "#ffffff";
  const text = isDark ? "#e8eef8" : "#1a1a2e";
  const muted = isDark ? "#94a3b8" : "#6b7280";
  const border = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.1)";
  const reportUrl = typeof window !== "undefined"
    ? `${window.location.origin}/report/${params.id}`
    : `/report/${params.id}`;

  if (error) {
    return (
      <div style={{ background: bg, color: text, padding: "2rem", textAlign: "center", fontFamily: "Inter, system-ui, sans-serif" }}>
        <p style={{ fontSize: "0.85rem", color: muted }}>Report not found</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div style={{ background: bg, color: text, padding: "2rem", textAlign: "center", fontFamily: "Inter, system-ui, sans-serif" }}>
        <p style={{ fontSize: "0.85rem", color: muted }}>Loading...</p>
      </div>
    );
  }

  const score = headlineScore(report);
  const risk = riskLevel(score);

  return (
    <div
      style={{
        background: bg,
        color: text,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        padding: "1.25rem 1.5rem",
        borderRadius: "12px",
        border: `1px solid ${border}`,
        maxWidth: "320px",
        boxSizing: "border-box",
      }}
    >
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <span style={{ fontSize: "0.65rem", fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase" as const, color: muted }}>
          Livability Score
        </span>
        <span
          style={{
            fontSize: "0.65rem",
            fontWeight: 700,
            padding: "0.15em 0.5em",
            borderRadius: "4px",
            background: `${risk.color}18`,
            color: risk.color,
            border: `1px solid ${risk.color}40`,
          }}
        >
          {risk.label}
        </span>
      </div>

      {/* Score */}
      <div style={{ fontSize: "2.5rem", fontWeight: 800, lineHeight: 1, letterSpacing: "-0.03em", color: risk.color }}>
        {score}
      </div>

      {/* Address */}
      <p style={{
        fontSize: "0.78rem",
        color: muted,
        margin: "0.5rem 0 0",
        whiteSpace: "nowrap" as const,
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}>
        {report.address}
      </p>

      {/* Confidence */}
      <p style={{ fontSize: "0.7rem", color: muted, margin: "0.25rem 0 0.75rem", opacity: 0.7 }}>
        Confidence: {report.confidence} &middot; {report.mode === "demo" ? "Demo" : "Live data"}
      </p>

      {/* CTA */}
      <a
        href={reportUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: "block",
          textAlign: "center" as const,
          fontSize: "0.78rem",
          fontWeight: 600,
          color: isDark ? "#a5b4fc" : "#4f46e5",
          textDecoration: "none",
          padding: "0.4rem 0",
          borderTop: `1px solid ${border}`,
        }}
      >
        View full report &rarr;
      </a>
    </div>
  );
}
