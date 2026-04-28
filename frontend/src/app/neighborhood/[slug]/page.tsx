"use client";

/**
 * frontend/src/app/neighborhood/[slug]/page.tsx
 * task: data-026
 *
 * SEO-indexed neighborhood heat map page.
 * Shows all live disruption projects on a Leaflet map with markers
 * colored by impact type, plus a project list and neighborhood summary.
 */

import React, { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { fetchNeighborhood, NeighborhoodProject, NeighborhoodResponse } from "@/lib/api";
import { impactTypeLabel } from "@/lib/score-utils";

// Impact type → marker color mapping
const IMPACT_COLORS: Record<string, string> = {
  traffic: "#e63946",
  noise: "#f4a261",
  dust: "#a8c5da",
  utility: "#6a4c93",
  construction: "#2a9d8f",
};

const STADIA_MAPS_API_KEY = process.env.NEXT_PUBLIC_STADIA_MAPS_API_KEY?.trim();
const NEIGHBORHOOD_TILE_LAYER = STADIA_MAPS_API_KEY
  ? {
      url: `https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png?api_key=${encodeURIComponent(STADIA_MAPS_API_KEY)}`,
      attribution:
        '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      subdomains: undefined,
    }
  : {
      url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
    };

function getMarkerColor(impactType: string | null): string {
  if (!impactType) return "#888";
  return IMPACT_COLORS[impactType.toLowerCase()] ?? "#888";
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ---------------------------------------------------------------------------
// Map component (client-only, SSR-safe via dynamic import inside useEffect)
// ---------------------------------------------------------------------------

type NeighborhoodMapProps = {
  center: { lat: number; lon: number };
  projects: NeighborhoodProject[];
};

function NeighborhoodMap({ center, projects }: NeighborhoodMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    if (mapRef.current) {
      (mapRef.current as { remove(): void }).remove();
      mapRef.current = null;
    }

    import("leaflet").then((L) => {
      if (!containerRef.current) return;

      const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images/";
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconUrl: `${iconBase}marker-icon.png`,
        iconRetinaUrl: `${iconBase}marker-icon-2x.png`,
        shadowUrl: `${iconBase}marker-shadow.png`,
      });

      const map = L.map(containerRef.current).setView([center.lat, center.lon], 14);

      // Public demo maps must not render provider auth-error tiles. Use the
      // same public CARTO fallback as the main app map unless Stadia is keyed.
      L.tileLayer(NEIGHBORHOOD_TILE_LAYER.url, {
        attribution: NEIGHBORHOOD_TILE_LAYER.attribution,
        maxZoom: 20,
        subdomains: NEIGHBORHOOD_TILE_LAYER.subdomains,
      }).addTo(map);

      // Add a marker for each project, colored by impact type
      for (const project of projects) {
        if (project.lat == null || project.lon == null) continue;

        const color = getMarkerColor(project.impact_type);
        const circleMarker = L.circleMarker([project.lat, project.lon], {
          radius: 8,
          fillColor: color,
          color: "#fff",
          weight: 1.5,
          opacity: 1,
          fillOpacity: 0.85,
        });

        const label = project.title ?? project.project_id;
        const type = impactTypeLabel(project.impact_type);
        circleMarker.bindPopup(
          `<strong>${label}</strong><br/>` +
          `Type: ${type}<br/>` +
          `Status: ${project.status}<br/>` +
          `${project.start_date ? `From: ${formatDate(project.start_date)}` : ""}` +
          `${project.end_date ? ` · To: ${formatDate(project.end_date)}` : ""}`
        );
        circleMarker.addTo(map);
      }

      mapRef.current = map;
    });

    return () => {
      if (mapRef.current) {
        (mapRef.current as { remove(): void }).remove();
        mapRef.current = null;
      }
    };
  }, [center, projects]);

  return (
    <>
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div
        ref={containerRef}
        style={{ height: "420px", width: "100%", borderRadius: "6px" }}
        aria-label="Neighborhood disruption project map"
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------

function ImpactLegend() {
  const entries = Object.entries(IMPACT_COLORS).concat([["other", "#888"]]);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", marginTop: "8px" }}>
      {entries.map(([type, color]) => (
        <span key={type} style={{ display: "flex", alignItems: "center", gap: "5px", fontSize: "13px" }}>
          <span style={{
            display: "inline-block",
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            background: color,
            border: "1px solid rgba(0,0,0,0.15)",
          }} />
          {type.charAt(0).toUpperCase() + type.slice(1)}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Project list
// ---------------------------------------------------------------------------

function ProjectList({ projects }: { projects: NeighborhoodProject[] }) {
  if (projects.length === 0) {
    return (
      <p style={{ color: "var(--color-muted, #888)", fontSize: "14px" }}>
        No active signals in this neighborhood right now — check back after the next daily data refresh at 06:00 UTC.
      </p>
    );
  }

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "10px" }}>
      {projects.map((p) => {
        const color = getMarkerColor(p.impact_type);
        return (
          <li
            key={p.project_id}
            style={{
              padding: "12px 14px",
              borderRadius: "6px",
              background: "var(--surface-raised, #f8f9fa)",
              borderLeft: `4px solid ${color}`,
            }}
          >
            <div style={{ fontWeight: 600, fontSize: "14px", marginBottom: "2px" }}>
              {p.title ?? p.project_id}
            </div>
            <div style={{ fontSize: "12px", color: "var(--color-muted, #666)", display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <span>Type: {impactTypeLabel(p.impact_type)}</span>
              <span>Source: {p.source}</span>
              {p.start_date && <span>From: {formatDate(p.start_date)}</span>}
              {p.end_date && <span>To: {formatDate(p.end_date)}</span>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function NeighborhoodLoadingState() {
  const skeletonRows = [
    { width: "82%" },
    { width: "64%" },
    { width: "74%" },
  ];

  return (
    <section
      aria-live="polite"
      aria-label="Loading neighborhood data"
      style={{
        marginTop: "40px",
        padding: "24px",
        borderRadius: "10px",
        border: "1px solid var(--border-subtle, #e5e7eb)",
        background: "var(--surface-raised, #f8fafc)",
        boxShadow: "0 18px 45px rgba(15, 23, 42, 0.08)",
      }}
    >
      <p
        style={{
          margin: "0 0 8px",
          fontSize: "12px",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--color-muted, #64748b)",
        }}
      >
        Livability Risk Engine
      </p>
      <h1 style={{ margin: "0 0 20px", fontSize: "24px", lineHeight: 1.2 }}>
        Loading neighborhood data…
      </h1>
      <div
        style={{
          height: "260px",
          borderRadius: "8px",
          background:
            "linear-gradient(135deg, rgba(59,130,246,0.16), rgba(148,163,184,0.10))",
          marginBottom: "18px",
        }}
      />
      <div style={{ display: "grid", gap: "10px" }}>
        {skeletonRows.map((row, index) => (
          <div
            key={index}
            style={{
              width: row.width,
              height: "14px",
              borderRadius: "999px",
              background: "rgba(148, 163, 184, 0.28)",
            }}
          />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NeighborhoodPage() {
  const params = useParams<{ slug: string }>();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  const [data, setData] = useState<NeighborhoodResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    fetchNeighborhood(slug).then((result) => {
      if (!result) {
        setNotFound(true);
      } else {
        setData(result);
      }
      setLoading(false);
    });
  }, [slug]);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: "960px", margin: "0 auto", padding: "32px 24px" }}>
      <a href="/" style={{ fontSize: "13px", color: "var(--color-muted, #666)", textDecoration: "none" }}>
        ← Livability Risk Engine
      </a>

      {loading && (
        <NeighborhoodLoadingState />
      )}

      {!loading && notFound && (
        <div style={{ marginTop: "48px" }}>
          <h1 style={{ fontSize: "24px", fontWeight: 700, marginBottom: "8px" }}>Neighborhood not found</h1>
          <p style={{ color: "var(--color-muted, #666)" }}>
            The neighborhood <code>{slug}</code> does not exist.{" "}
            <a href="/" style={{ color: "inherit" }}>Go back home.</a>
          </p>
        </div>
      )}

      {!loading && data && (
        <>
          <div style={{ marginTop: "24px", marginBottom: "8px" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--color-muted, #888)" }}>
              Chicago Neighborhood · Disruption Intelligence
            </span>
          </div>

          <h1 style={{ fontSize: "28px", fontWeight: 800, marginBottom: "6px" }}>{data.name}</h1>
          <p style={{ fontSize: "15px", color: "var(--color-muted, #555)", marginBottom: "28px", maxWidth: "600px" }}>
            {data.description}
          </p>

          {/* Summary bar */}
          <div style={{
            display: "flex",
            gap: "24px",
            padding: "14px 18px",
            background: "var(--surface-raised, #f8f9fa)",
            borderRadius: "8px",
            marginBottom: "24px",
            flexWrap: "wrap",
          }}>
            <div>
              <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#888", marginBottom: "2px" }}>Active projects</div>
              <div style={{ fontSize: "20px", fontWeight: 700 }}>{data.project_count}</div>
            </div>
            <div>
              <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#888", marginBottom: "2px" }}>Data mode</div>
              <div style={{ fontSize: "14px", fontWeight: 600, color: data.mode === "live" ? "#2a9d8f" : "#888" }}>
                {data.mode === "live" ? "Live" : "Demo"}
              </div>
            </div>
            {data.mode === "demo" && (
              <div style={{ fontSize: "13px", color: "#888", alignSelf: "center" }}>
                Connect a live database to see real project data.
              </div>
            )}
          </div>

          {/* Map */}
          <div style={{ marginBottom: "16px" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 700, marginBottom: "8px" }}>Project map</h2>
            <NeighborhoodMap center={data.center} projects={data.projects} />
            <ImpactLegend />
          </div>

          {/* Project list */}
          <div style={{ marginTop: "32px" }}>
            <h2 style={{ fontSize: "16px", fontWeight: 700, marginBottom: "12px" }}>
              Active projects ({data.project_count})
            </h2>
            <ProjectList projects={data.projects} />
          </div>
        </>
      )}
    </main>
  );
}
