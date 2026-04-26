/**
 * /neighborhood/[slug]/best-streets
 * task: data-014
 *
 * Static SEO page — server component, no "use client".
 * Pre-rendered at build time for all 20 Chicago neighborhoods via
 * generateStaticParams. Revalidated every 24 h (ISR).
 *
 * Title format : "Quietest Streets in [Neighborhood], Chicago — Updated [Month Year]"
 * Meta desc    : unique, generated from actual block data by the backend.
 */

import type { Metadata } from "next";
import {
  ALL_NEIGHBORHOOD_SLUGS,
  BestStreetsBlock,
  BestStreetsResponse,
  fetchBestStreets,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Static params — one page per neighborhood slug
// ---------------------------------------------------------------------------

export function generateStaticParams() {
  return ALL_NEIGHBORHOOD_SLUGS.map((slug) => ({ slug }));
}

// ---------------------------------------------------------------------------
// Metadata — title + unique meta description from live data
// ---------------------------------------------------------------------------

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await fetchBestStreets(slug);
  if (!data) {
    return {
      title: "Quietest Streets in Chicago — Livability Intelligence",
      description: "Block-level disruption intelligence for Chicago neighborhoods.",
    };
  }

  const monthYear = formatMonthYear(data.last_updated);
  const title = `Quietest Streets in ${data.name}, Chicago — Updated ${monthYear}`;
  const canonical = `https://livabilityrisk.com/neighborhood/${slug}/best-streets`;

  return {
    title,
    description: data.meta_description,
    openGraph: {
      title,
      description: data.meta_description,
      url: canonical,
      siteName: "Livability Intelligence",
      type: "article",
    },
    twitter: {
      card: "summary",
      title,
      description: data.meta_description,
    },
    alternates: { canonical },
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatMonthYear(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return "recently";
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return iso;
  }
}

function scoreColor(score: number): string {
  if (score <= 20) return "#10b981"; // green
  if (score <= 45) return "#f59e0b"; // amber
  if (score <= 65) return "#ef4444"; // red
  return "#7c3aed";                   // purple — severe
}

function scoreBand(score: number): string {
  if (score <= 20) return "Minimal";
  if (score <= 45) return "Low";
  if (score <= 65) return "Moderate";
  if (score <= 80) return "High";
  return "Severe";
}

// ---------------------------------------------------------------------------
// Sub-components (server-renderable, no hooks)
// ---------------------------------------------------------------------------

function ScoreBar({ score }: { score: number }) {
  const color = scoreColor(score);
  return (
    <div
      aria-label={`Score ${score} out of 100`}
      style={{ display: "flex", alignItems: "center", gap: "10px" }}
    >
      <div
        style={{
          flex: 1,
          height: "6px",
          borderRadius: "3px",
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${score}%`,
            height: "100%",
            background: color,
            borderRadius: "3px",
          }}
        />
      </div>
      <span
        style={{
          fontSize: "0.78rem",
          fontWeight: 700,
          color,
          minWidth: "26px",
          textAlign: "right",
        }}
      >
        {score}
      </span>
    </div>
  );
}

function BlockList({
  blocks,
  variant,
}: {
  blocks: BestStreetsBlock[];
  variant: "quiet" | "busy";
}) {
  const isQuiet = variant === "quiet";
  const accentColor = isQuiet ? "#10b981" : "#ef4444";

  if (blocks.length === 0) {
    return (
      <p style={{ color: "var(--text-muted, #64748b)", fontSize: "0.85rem" }}>
        No block data available.
      </p>
    );
  }

  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "10px" }}>
      {blocks.map((block, i) => (
        <li
          key={`${block.block}-${i}`}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "14px",
            padding: "14px 16px",
            borderRadius: "10px",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderLeft: `3px solid ${scoreColor(block.avg_score)}`,
          }}
        >
          {/* Rank */}
          <span
            style={{
              fontSize: "0.68rem",
              fontWeight: 700,
              color: accentColor,
              minWidth: "18px",
              paddingTop: "2px",
            }}
          >
            #{i + 1}
          </span>

          {/* Block info */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <p
              style={{
                margin: "0 0 6px",
                fontWeight: 600,
                fontSize: "0.9rem",
                color: "var(--text, #f1f5f9)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {block.block}
            </p>
            <ScoreBar score={block.avg_score} />
            <p
              style={{
                margin: "5px 0 0",
                fontSize: "0.72rem",
                color: "var(--text-muted, #64748b)",
              }}
            >
              {scoreBand(block.avg_score)} disruption
              {block.active_projects > 0
                ? ` · ${block.active_projects} active permit${block.active_projects !== 1 ? "s" : ""}`
                : " · No active permits"}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Fallback page — backend unreachable
// ---------------------------------------------------------------------------

function NotAvailable({ slug }: { slug: string }) {
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: "760px", margin: "0 auto", padding: "40px 24px" }}>
      <a href="/" style={{ fontSize: "13px", color: "#64748b", textDecoration: "none" }}>
        ← Livability Intelligence
      </a>
      <h1 style={{ marginTop: "32px", fontSize: "24px", fontWeight: 800 }}>
        Data unavailable
      </h1>
      <p style={{ color: "#64748b" }}>
        Block data for <code>{slug}</code> could not be loaded. Try again shortly or{" "}
        <a href="/" style={{ color: "#84a6ff" }}>run a live lookup</a>.
      </p>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function BestStreetsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug: pageSlug } = await params;
  const data: BestStreetsResponse | null = await fetchBestStreets(pageSlug);

  if (!data) return <NotAvailable slug={pageSlug} />;

  const { name, quietest_blocks, busiest_blocks, last_updated, mode, slug } = data;
  const monthYear = formatMonthYear(last_updated);
  const canonicalUrl = `https://livabilityrisk.com/neighborhood/${slug}/best-streets`;
  const iframeSnippet = `<iframe src="${canonicalUrl}?embed=1" width="640" height="520" frameborder="0" loading="lazy" title="Quietest streets in ${name}, Chicago"></iframe>`;

  return (
    <main
      style={{
        fontFamily: "system-ui, -apple-system, sans-serif",
        maxWidth: "800px",
        margin: "0 auto",
        padding: "40px 24px 80px",
        color: "var(--text, #f1f5f9)",
        background: "var(--bg, #07101d)",
        minHeight: "100vh",
      }}
    >
      {/* ── Breadcrumb ───────────────────────────────────────────────── */}
      <nav aria-label="Breadcrumb" style={{ fontSize: "13px", marginBottom: "28px", display: "flex", gap: "6px", color: "#64748b" }}>
        <a href="/" style={{ color: "#64748b", textDecoration: "none" }}>Livability Intelligence</a>
        <span>›</span>
        <a href={`/neighborhood/${slug}`} style={{ color: "#64748b", textDecoration: "none" }}>
          {name}
        </a>
        <span>›</span>
        <span style={{ color: "#94a3b8" }}>Best Streets</span>
      </nav>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <div style={{ marginBottom: "32px" }}>
        <p
          style={{
            fontSize: "0.67rem",
            fontWeight: 700,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "#64748b",
            marginBottom: "8px",
          }}
        >
          Chicago Neighborhood · Block-Level Disruption Intelligence
        </p>
        <h1
          style={{
            fontSize: "clamp(1.4rem, 4vw, 2rem)",
            fontWeight: 800,
            lineHeight: 1.2,
            margin: "0 0 12px",
          }}
        >
          Quietest Streets in {name}, Chicago
        </h1>
        <p style={{ fontSize: "0.9rem", color: "#94a3b8", margin: "0 0 16px", maxWidth: "600px" }}>
          {data.meta_description}
        </p>

        {/* Meta row */}
        <div style={{ display: "flex", gap: "20px", flexWrap: "wrap", alignItems: "center" }}>
          <span
            style={{
              fontSize: "0.72rem",
              color: "#64748b",
              display: "flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            <span aria-hidden="true">🕐</span>
            Last updated: {formatDate(last_updated)}
          </span>
          {mode === "demo" && (
            <span
              style={{
                fontSize: "0.67rem",
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(245,158,11,0.12)",
                border: "1px solid rgba(245,158,11,0.25)",
                color: "#f59e0b",
              }}
            >
              Demo data — connect a live database for real block scores
            </span>
          )}
        </div>
      </div>

      {/* ── Two-column grid ──────────────────────────────────────────── */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "24px",
          marginBottom: "40px",
        }}
      >
        {/* Quietest blocks */}
        <section>
          <h2
            style={{
              fontSize: "0.78rem",
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "#10b981",
              marginBottom: "14px",
            }}
          >
            5 Quietest Blocks
          </h2>
          <BlockList blocks={quietest_blocks} variant="quiet" />
        </section>

        {/* Highest-disruption blocks */}
        <section>
          <h2
            style={{
              fontSize: "0.78rem",
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "#ef4444",
              marginBottom: "14px",
            }}
          >
            5 Highest-Disruption Blocks
          </h2>
          <BlockList blocks={busiest_blocks} variant="busy" />
        </section>
      </div>

      {/* ── CTA ─────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: "20px 24px",
          borderRadius: "12px",
          background: "rgba(132,166,255,0.06)",
          border: "1px solid rgba(132,166,255,0.15)",
          marginBottom: "40px",
          display: "flex",
          gap: "16px",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: "200px" }}>
          <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: "0.9rem" }}>
            Check a specific address in {name}
          </p>
          <p style={{ margin: 0, fontSize: "0.78rem", color: "#94a3b8" }}>
            Get a real-time disruption score for any Illinois address in under 10 seconds.
          </p>
        </div>
        <a
          href="/"
          style={{
            display: "inline-block",
            padding: "10px 20px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #84a6ff 0%, #5f7cff 100%)",
            color: "#07101d",
            fontWeight: 700,
            fontSize: "0.85rem",
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          Run a lookup →
        </a>
      </div>

      {/* ── Share + Embed ────────────────────────────────────────────── */}
      <section style={{ marginBottom: "40px" }}>
        <h2
          style={{
            fontSize: "0.78rem",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "#64748b",
            marginBottom: "16px",
          }}
        >
          Share &amp; Embed
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Shareable link */}
          <div>
            <p style={{ fontSize: "0.72rem", color: "#64748b", marginBottom: "6px" }}>
              Shareable link
            </p>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "10px 14px",
                borderRadius: "8px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                fontFamily: "monospace",
                fontSize: "0.78rem",
                color: "#94a3b8",
                overflowX: "auto",
              }}
            >
              {canonicalUrl}
            </div>
          </div>

          {/* Embed snippet */}
          <div>
            <p style={{ fontSize: "0.72rem", color: "#64748b", marginBottom: "6px" }}>
              Embed widget — paste into any HTML page
            </p>
            <pre
              style={{
                margin: 0,
                padding: "12px 14px",
                borderRadius: "8px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                fontFamily: "monospace",
                fontSize: "0.73rem",
                color: "#94a3b8",
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {iframeSnippet}
            </pre>
          </div>
        </div>
      </section>

      {/* ── Methodology note ─────────────────────────────────────────── */}
      <footer
        style={{
          paddingTop: "20px",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          fontSize: "0.72rem",
          color: "#475569",
          lineHeight: 1.7,
        }}
      >
        <p style={{ margin: "0 0 4px" }}>
          <strong style={{ color: "#64748b" }}>Methodology.</strong>{" "}
          Block scores are computed by aggregating active Chicago permit and street closure signals
          within ~90-meter grid cells. Each signal type contributes a weighted score (full closure
          = 35 pts, construction = 15 pts, light permit = 8 pts). Cells are ranked lowest-to-highest
          to identify the quietest and most disrupted blocks. Scores range 0–100.
        </p>
        <p style={{ margin: "8px 0 0" }}>
          Data sourced from Chicago Permits and Chicago Street Closures datasets via City of Chicago
          Data Portal. Block scores reflect near-term permit conditions, not long-term neighborhood
          quality. Updated {monthYear}.
        </p>
      </footer>
    </main>
  );
}
