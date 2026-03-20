"use client";

// data-026: Neighborhood disruption heat map page
// URL: /neighborhood/<slug>  (e.g. /neighborhood/west-loop)
// Fetches all active projects in the neighborhood and renders a Leaflet map
// with markers colored by impact type, plus a ranked project list.

import React, { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Card, Container, Section } from "@/components/shell";

// Leaflet must be dynamically imported (no SSR).
const MapView = dynamic(
  () => import("@/components/map-view").then((m) => m.MapView),
  { ssr: false },
);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Project = {
  project_id: string;
  source: string;
  impact_type: string;
  title: string;
  notes: string | null;
  start_date: string | null;
  end_date: string | null;
  status: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
};

type BBox = { min_lat: number; min_lon: number; max_lat: number; max_lon: number };

type NeighborhoodResponse = {
  slug: string;
  name: string;
  description: string;
  bbox: BBox;
  projects: Project[];
  mode: "live" | "demo";
  available_neighborhoods: { slug: string; name: string }[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const IMPACT_LABELS: Record<string, string> = {
  closure_full: "Full closure",
  closure_multi_lane: "Multi-lane closure",
  closure_single_lane: "Single-lane closure",
  demolition: "Demolition",
  construction: "Construction",
  light_permit: "Light permit",
};

const IMPACT_ORDER: Record<string, number> = {
  closure_full: 1,
  closure_multi_lane: 2,
  closure_single_lane: 3,
  demolition: 4,
  construction: 5,
  light_permit: 6,
};

function impactLabel(type: string): string {
  return IMPACT_LABELS[type] ?? type;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[Number(m) - 1]} ${Number(d)}, ${y}`;
}

function bboxCenter(bbox: BBox): { lat: number; lon: number } {
  return {
    lat: (bbox.min_lat + bbox.max_lat) / 2,
    lon: (bbox.min_lon + bbox.max_lon) / 2,
  };
}

const SLUGS = [
  "west-loop","wicker-park","logan-square","river-north",
  "lincoln-park","pilsen","bronzeville","uptown",
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function NeighborhoodPage({ params }: { params: { slug: string } }) {
  const [data, setData] = useState<NeighborhoodResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("all");

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

  useEffect(() => {
    fetch(`${apiBase}/neighborhood/${encodeURIComponent(params.slug)}`, { cache: "no-store" })
      .then(async (resp) => {
        if (resp.status === 404) { setNotFound(true); return; }
        if (!resp.ok) { setError(`Backend error (${resp.status})`); return; }
        setData(await resp.json());
      })
      .catch(() => setError("Could not reach backend."));
  }, [params.slug, apiBase]);

  const projects = data?.projects ?? [];
  const sorted = [...projects].sort(
    (a, b) => (IMPACT_ORDER[a.impact_type] ?? 9) - (IMPACT_ORDER[b.impact_type] ?? 9),
  );
  const filtered = filterType === "all" ? sorted : sorted.filter((p) => p.impact_type === filterType);
  const impactTypes = Array.from(new Set(projects.map((p) => p.impact_type))).sort(
    (a, b) => (IMPACT_ORDER[a] ?? 9) - (IMPACT_ORDER[b] ?? 9),
  );
  const center = data ? bboxCenter(data.bbox) : null;

  // Count by type for the summary chips.
  const typeCounts = projects.reduce<Record<string, number>>((acc, p) => {
    acc[p.impact_type] = (acc[p.impact_type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <main>
      <Container>
        <div className="report-header">
          <a href="/" className="report-back-link">← Back to Livability Risk Engine</a>
        </div>

        {/* Neighborhood nav */}
        <div className="neighborhood-nav">
          {SLUGS.map((s) => (
            <a
              key={s}
              href={`/neighborhood/${s}`}
              className={`neighborhood-nav-chip${s === params.slug ? " neighborhood-nav-chip--active" : ""}`}
            >
              {s.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </a>
          ))}
        </div>

        {!data && !notFound && !error && (
          <Section eyebrow="Loading" title="Fetching neighborhood data…">
            <Card className="empty-state"><p className="empty-kicker">Please wait</p></Card>
          </Section>
        )}

        {notFound && (
          <Section eyebrow="Not found" title="Unknown neighborhood">
            <Card className="empty-state">
              <p className="empty-kicker">404</p>
              <h3>That neighborhood slug isn&apos;t recognized.</h3>
              <p><a href="/neighborhood/west-loop">Try West Loop →</a></p>
            </Card>
          </Section>
        )}

        {error && (
          <Section eyebrow="Error" title="Could not load data">
            <Card className="empty-state"><p>{error}</p></Card>
          </Section>
        )}

        {data && (
          <>
            <Section
              eyebrow="Neighborhood"
              title={data.name}
              description={data.description}
            >
              {/* Summary chips */}
              <div className="neighborhood-summary-chips">
                <span className="neighborhood-chip neighborhood-chip--total">
                  {projects.length} active projects
                </span>
                {Object.entries(typeCounts).sort((a,b) => (IMPACT_ORDER[a[0]]??9)-(IMPACT_ORDER[b[0]]??9)).map(([type, count]) => (
                  <span key={type} className={`neighborhood-chip neighborhood-chip--${type.replace(/_/g,"-")}`}>
                    {count} {impactLabel(type).toLowerCase()}
                  </span>
                ))}
                {data.mode === "demo" && (
                  <span className="neighborhood-chip neighborhood-chip--demo">Demo mode — no live data</span>
                )}
              </div>

              {/* Map */}
              {center && (
                <Card className="detail-card map-card">
                  <div className="map-card-head">
                    <div>
                      <p className="map-kicker">Spatial context</p>
                      <h2>Active projects in {data.name}</h2>
                    </div>
                    <span className="map-badge">OpenStreetMap</span>
                  </div>
                  <MapView latitude={center.lat} longitude={center.lon} address={data.name} />
                  <p className="map-copy">
                    Map centered on {data.name}. Zoom in to see individual project locations.
                  </p>
                </Card>
              )}

              {/* Project list */}
              {projects.length > 0 ? (
                <Card className="detail-card">
                  <div className="neighborhood-list-head">
                    <h2>All active projects ({filtered.length})</h2>
                    <div className="neighborhood-filter-row">
                      <button
                        type="button"
                        className={`neighborhood-filter-btn${filterType === "all" ? " neighborhood-filter-btn--active" : ""}`}
                        onClick={() => setFilterType("all")}
                      >
                        All
                      </button>
                      {impactTypes.map((type) => (
                        <button
                          key={type}
                          type="button"
                          className={`neighborhood-filter-btn${filterType === type ? " neighborhood-filter-btn--active" : ""}`}
                          onClick={() => setFilterType(type)}
                        >
                          {impactLabel(type)} ({typeCounts[type]})
                        </button>
                      ))}
                    </div>
                  </div>

                  <ul className="neighborhood-project-list">
                    {filtered.map((p) => (
                      <li key={p.project_id} className="neighborhood-project-item">
                        <div className="neighborhood-project-head">
                          <span className={`impact-badge impact-badge--${p.impact_type.includes("closure") ? "high" : p.impact_type === "demolition" ? "medium" : "low"}`}>
                            {impactLabel(p.impact_type)}
                          </span>
                          <span className={`permit-status permit-status--${p.status}`}>{p.status}</span>
                        </div>
                        <p className="neighborhood-project-title">{p.title}</p>
                        {p.address && <p className="neighborhood-project-address">{p.address}</p>}
                        <p className="neighborhood-project-dates">
                          {formatDate(p.start_date)} → {formatDate(p.end_date)}
                        </p>
                        {p.notes && <p className="neighborhood-project-notes">{p.notes}</p>}
                        <div className="neighborhood-project-actions">
                          <a
                            href={`/?address=${encodeURIComponent(p.address ?? p.title)}`}
                            className="compare-link"
                          >
                            Score this address →
                          </a>
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : (
                <Card className="empty-state">
                  <p className="empty-kicker">No data</p>
                  <h3>No active projects found in {data.name}.</h3>
                  {data.mode === "demo" && (
                    <p>Connect a live database to see real permit and closure data.</p>
                  )}
                </Card>
              )}
            </Section>
          </>
        )}
      </Container>
    </main>
  );
}
