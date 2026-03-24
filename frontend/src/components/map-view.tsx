"use client";

import { useEffect, useRef, useState } from "react";

import type { NearbySignal, TopRiskDetail } from "@/lib/api";

type MapMode = "signals" | "heatmap";

type MapViewProps = {
  latitude: number;
  longitude: number;
  address: string;
  signals?: NearbySignal[];
  topRiskDetails?: TopRiskDetail[];
  isPro?: boolean;
};

// ─── Impact-type colour palette ───────────────────────────────────────────────
const IMPACT_COLOR: Record<string, string> = {
  closure_full:        "#ff3b30",
  closure_multi_lane:  "#ff6b35",
  closure_single_lane: "#ff9f0a",
  demolition:          "#bf5af2",
  construction:        "#ffd60a",
  light_permit:        "#30d158",
};
const DEFAULT_COLOR = "#8da5ff";

// ─── Signal-circle radius (meters) ───────────────────────────────────────────
const SIGNAL_RADIUS: Record<string, number> = {
  closure_full:        90,
  closure_multi_lane:  75,
  closure_single_lane: 55,
  demolition:          65,
  construction:        50,
  light_permit:        38,
};
const DEFAULT_SIGNAL_RADIUS = 45;

// ─── Heatmap outer blob radius (meters) ──────────────────────────────────────
const HEAT_RADIUS: Record<string, number> = {
  closure_full:        200,
  closure_multi_lane:  175,
  closure_single_lane: 145,
  demolition:          165,
  construction:        130,
  light_permit:        95,
};
const DEFAULT_HEAT_RADIUS = 120;

// ─── Labels ───────────────────────────────────────────────────────────────────
const IMPACT_LABEL: Record<string, string> = {
  closure_full:        "Full street closure",
  closure_multi_lane:  "Multi-lane closure",
  closure_single_lane: "Lane / curb closure",
  demolition:          "Demolition / excavation",
  construction:        "Active construction",
  light_permit:        "Permitted work",
};

const SOURCE_LABEL: Record<string, string> = {
  chicago_closures:        "CDOT Street Closures",
  chicago_permits:         "Chicago Building Permits",
  idot_road_projects:      "IDOT Road Construction",
  chicago_311_requests:    "Chicago 311",
  chicago_film_permits:    "Chicago Film Permits",
  chicago_special_events:  "Chicago Special Events",
  cta_alerts:              "CTA Service Alerts",
  chicago_traffic_crashes: "Chicago Traffic Crashes",
  chicago_divvy_stations:  "Divvy Bike Stations",
};

function impactLabel(t: string) { return IMPACT_LABEL[t] ?? t; }
function impactColor(t: string) { return IMPACT_COLOR[t] ?? DEFAULT_COLOR; }
function signalRadius(t: string) { return SIGNAL_RADIUS[t] ?? DEFAULT_SIGNAL_RADIUS; }
function heatRadius(t: string) { return HEAT_RADIUS[t] ?? DEFAULT_HEAT_RADIUS; }
function sourceLabel(s: string) { return SOURCE_LABEL[s] ?? s; }

function signalOpacity(weight: number): number {
  return Math.min(0.72, Math.max(0.2, (weight / 45) * 0.72));
}

function metersToFeet(m: number): number {
  return Math.round(m * 3.28084);
}

function formatDateRange(start?: string | null, end?: string | null): string {
  if (!start && !end) return "Dates unknown";
  const fmt = (iso: string) => {
    const [y, m, d] = iso.split("-");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[Number(m) - 1]} ${Number(d)}, ${y}`;
  };
  if (start && end) return `${fmt(start)} – ${fmt(end)}`;
  if (start) return `From ${fmt(start)}`;
  return `Until ${fmt(end!)}`;
}

function isSignalActiveOnDay(signal: NearbySignal, forecastDate: Date): boolean {
  const parse = (iso: string) => new Date(iso + "T00:00:00Z");
  if (signal.start_date && parse(signal.start_date) > forecastDate) return false;
  if (signal.end_date && parse(signal.end_date) < forecastDate) return false;
  return true;
}

const TOTAL_FORECAST_DAYS = 30;
const FORECAST_STEP_MS = 420;

// ─── Toggle button sub-component ──────────────────────────────────────────────
function ToggleBtn({
  active,
  onClick,
  first,
  children,
}: {
  active: boolean;
  onClick: () => void;
  first?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: "5px 13px",
        fontSize: "0.74rem",
        fontWeight: 600,
        border: "none",
        borderLeft: first ? undefined : "1px solid rgba(255,255,255,0.08)",
        cursor: "pointer",
        background: active ? "var(--accent, #3b82f6)" : "transparent",
        color: active ? "#fff" : "var(--text-muted, #94a3b8)",
        transition: "background 0.14s, color 0.14s",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────
export function MapView({
  latitude,
  longitude,
  address,
  signals = [],
  topRiskDetails: _topRiskDetails = [],
  isPro = false,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const signalGroupRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const heatGroupRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const leafletRef = useRef<any>(null);

  // mapVersion increments after the Leaflet async init completes, triggering
  // the layer-update effect which would otherwise see null refs.
  const [mapVersion, setMapVersion] = useState(0);
  const [mapMode, setMapMode] = useState<MapMode>("signals");
  const [forecastActive, setForecastActive] = useState(false);
  const [forecastDay, setForecastDay] = useState(0);
  const forecastTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Effect 1: Create / recreate map when coordinates change ──────────────
  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy any existing map before re-initialising.
    if (mapRef.current) {
      mapRef.current.remove();
      mapRef.current = null;
      signalGroupRef.current = null;
      heatGroupRef.current = null;
      leafletRef.current = null;
    }

    import("leaflet").then((L) => {
      if (!containerRef.current) return;

      // Fix webpack-mangled default icon URLs.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images/";
      L.Icon.Default.mergeOptions({
        iconUrl:       `${iconBase}marker-icon.png`,
        iconRetinaUrl: `${iconBase}marker-icon-2x.png`,
        shadowUrl:     `${iconBase}marker-shadow.png`,
      });

      const map = L.map(containerRef.current).setView([latitude, longitude], 15);

      L.tileLayer("https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 20,
      }).addTo(map);

      L.marker([latitude, longitude]).addTo(map).bindPopup(address).openPopup();

      signalGroupRef.current = L.layerGroup().addTo(map);
      heatGroupRef.current   = L.layerGroup(); // added/removed by layer effect
      leafletRef.current     = L;
      mapRef.current         = map;

      // Signal the layer-update effect that the map is ready.
      setMapVersion((v) => v + 1);
    });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
        signalGroupRef.current = null;
        heatGroupRef.current = null;
        leafletRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latitude, longitude, address]);

  // ── Effect 2: Rebuild layers whenever mode / signals / forecast changes ───
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const signalGroup = signalGroupRef.current;
    const heatGroup = heatGroupRef.current;
    if (!L || !map || !signalGroup || !heatGroup) return;

    signalGroup.clearLayers();
    heatGroup.clearLayers();

    // Compute which signals are active for the current forecast day.
    const baseDate = new Date();
    baseDate.setHours(0, 0, 0, 0);
    const forecastDate = new Date(baseDate);
    forecastDate.setDate(forecastDate.getDate() + forecastDay);

    const active = forecastActive
      ? signals.filter((s) => isSignalActiveOnDay(s, forecastDate))
      : signals;
    const faded = forecastActive
      ? signals.filter((s) => !isSignalActiveOnDay(s, forecastDate))
      : [];

    if (mapMode === "signals") {
      // ── Signal-circles mode ───────────────────────────────────────────────
      for (const s of active) {
        const color  = impactColor(s.impact_type);
        const radius = signalRadius(s.impact_type);
        const fill   = signalOpacity(s.weight);
        const distFt = metersToFeet(s.distance_m);
        const src    = s.source ? sourceLabel(s.source) : "City of Chicago";
        const dates  = formatDateRange(s.start_date, s.end_date);

        const popup = `
          <div style="font-family:system-ui,sans-serif;min-width:210px;max-width:250px">
            <div style="font-size:0.67rem;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;color:${color};margin-bottom:4px">${impactLabel(s.impact_type)}</div>
            <div style="font-size:0.87rem;font-weight:600;line-height:1.4;margin-bottom:8px">${s.title}</div>
            <div style="font-size:0.72rem;color:#888;line-height:1.7">
              <div><strong style="color:#aaa">Dates:</strong> ${dates}</div>
              <div><strong style="color:#aaa">Source:</strong> ${src}</div>
              <div><strong style="color:#aaa">Distance:</strong> ~${distFt} ft · ${s.severity_hint} severity</div>
            </div>
          </div>`;

        L.circle([s.lat, s.lon], {
          radius, color, fillColor: color, fillOpacity: fill,
          weight: 1.5, opacity: 0.75,
        }).bindPopup(popup).addTo(signalGroup);
      }

      // Faded (out-of-window) signals shown dimly.
      for (const s of faded) {
        const color  = impactColor(s.impact_type);
        const radius = signalRadius(s.impact_type);
        L.circle([s.lat, s.lon], {
          radius, color, fillColor: color,
          fillOpacity: 0.07, weight: 1, opacity: 0.18,
        }).addTo(signalGroup);
      }

      if (!map.hasLayer(signalGroup)) signalGroup.addTo(map);
      if (map.hasLayer(heatGroup)) map.removeLayer(heatGroup);

    } else {
      // ── Heatmap mode ──────────────────────────────────────────────────────
      for (const s of active) {
        const color = impactColor(s.impact_type);
        const r     = heatRadius(s.impact_type);
        // Outer diffuse blob
        L.circle([s.lat, s.lon], {
          radius: r, color: "transparent", fillColor: color,
          fillOpacity: 0.16, weight: 0,
        }).addTo(heatGroup);
        // Inner concentrated core
        L.circle([s.lat, s.lon], {
          radius: r * 0.42, color: "transparent", fillColor: color,
          fillOpacity: 0.28, weight: 0,
        }).addTo(heatGroup);
      }

      for (const s of faded) {
        const color = impactColor(s.impact_type);
        L.circle([s.lat, s.lon], {
          radius: heatRadius(s.impact_type), color: "transparent",
          fillColor: color, fillOpacity: 0.04, weight: 0,
        }).addTo(heatGroup);
      }

      if (!map.hasLayer(heatGroup)) heatGroup.addTo(map);
      if (map.hasLayer(signalGroup)) map.removeLayer(signalGroup);
    }
  }, [mapVersion, signals, mapMode, forecastDay, forecastActive]);

  // ── Effect 3: Start / stop forecast animation ─────────────────────────────
  useEffect(() => {
    if (forecastTimerRef.current) {
      clearInterval(forecastTimerRef.current);
      forecastTimerRef.current = null;
    }
    if (!forecastActive) {
      setForecastDay(0);
      return;
    }
    setForecastDay(0);
    forecastTimerRef.current = setInterval(() => {
      setForecastDay((d) => (d < TOTAL_FORECAST_DAYS ? d + 1 : d));
    }, FORECAST_STEP_MS);
    return () => {
      if (forecastTimerRef.current) clearInterval(forecastTimerRef.current);
    };
  }, [forecastActive]);

  // ── Effect 4: Auto-stop when animation completes ──────────────────────────
  useEffect(() => {
    if (forecastDay >= TOTAL_FORECAST_DAYS && forecastTimerRef.current) {
      clearInterval(forecastTimerRef.current);
      forecastTimerRef.current = null;
    }
  }, [forecastDay]);

  // ── Derived display values ────────────────────────────────────────────────
  const today = new Date();
  const forecastDateLabel = (() => {
    const d = new Date(today);
    d.setDate(d.getDate() + forecastDay);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  })();

  const forecastDone = forecastActive && forecastDay >= TOTAL_FORECAST_DAYS;
  const forecastBtnLabel = forecastActive
    ? forecastDone
      ? `✓ Done — click to replay`
      : `◼ Stop  ·  ${forecastDateLabel}`
    : "▶ 30-day forecast";

  return (
    <>
      {/* Leaflet CSS — loaded inline to stay SSR-safe */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />

      {/* ── Controls bar ─────────────────────────────────────────────────── */}
      <div style={{
        display: "flex", alignItems: "center", gap: "8px",
        marginBottom: "10px", flexWrap: "wrap",
      }}>
        {/* Mode toggle pill */}
        <div style={{
          display: "flex",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: "7px",
          overflow: "hidden",
          background: "rgba(255,255,255,0.04)",
        }}>
          <ToggleBtn first active={mapMode === "signals"} onClick={() => setMapMode("signals")}>
            Signal circles
          </ToggleBtn>
          <ToggleBtn active={mapMode === "heatmap"} onClick={() => setMapMode("heatmap")}>
            Disruption heatmap
          </ToggleBtn>
        </div>

        {/* Forecast button */}
        <button
          type="button"
          disabled={!isPro}
          title={isPro ? "Animate 30-day projected signal changes" : "30-day forecast is a Pro feature — upgrade to unlock"}
          onClick={() => {
            if (!isPro) return;
            if (forecastDone) {
              // replay
              setForecastActive(false);
              setTimeout(() => setForecastActive(true), 60);
            } else {
              setForecastActive((v) => !v);
            }
          }}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "5px",
            padding: "5px 13px",
            fontSize: "0.74rem",
            fontWeight: 600,
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "7px",
            cursor: isPro ? "pointer" : "not-allowed",
            background: forecastActive ? "rgba(124,58,237,0.85)" : "rgba(255,255,255,0.04)",
            color: forecastActive ? "#fff" : isPro ? "var(--text-muted, #94a3b8)" : "rgba(148,163,184,0.45)",
            transition: "background 0.14s, color 0.14s",
            whiteSpace: "nowrap",
          }}
          aria-pressed={forecastActive}
        >
          {forecastBtnLabel}
          {!isPro && (
            <span style={{
              fontSize: "0.58rem", fontWeight: 700,
              letterSpacing: "0.06em", textTransform: "uppercase",
              padding: "1px 5px", borderRadius: "3px",
              background: "#7c3aed", color: "#fff",
            }}>
              Pro
            </span>
          )}
        </button>

        {!isPro && (
          <a
            href="#pricing-section"
            style={{
              fontSize: "0.71rem", color: "#a78bfa",
              textDecoration: "none", fontWeight: 500,
            }}
          >
            Upgrade →
          </a>
        )}

        {/* Day counter shown while animating */}
        {forecastActive && !forecastDone && (
          <span style={{
            fontSize: "0.72rem", color: "#a78bfa", fontWeight: 600,
            letterSpacing: "0.03em",
          }}>
            Day {forecastDay} / {TOTAL_FORECAST_DAYS}
          </span>
        )}
      </div>

      {/* ── Map container ────────────────────────────────────────────────── */}
      <div style={{ position: "relative" }}>
        <div
          ref={containerRef}
          style={{ height: "420px", width: "100%", borderRadius: "var(--radius, 6px)" }}
          aria-label={`Map showing ${address} with ${signals.length} nearby signal${signals.length !== 1 ? "s" : ""}`}
        />

        {/* Forecast overlay badge */}
        {forecastActive && (
          <div style={{
            position: "absolute", top: "10px", right: "10px", zIndex: 1000,
            background: "rgba(109,40,217,0.9)", color: "#fff",
            padding: "5px 11px", borderRadius: "6px",
            fontSize: "0.75rem", fontWeight: 700,
            pointerEvents: "none", backdropFilter: "blur(4px)",
          }}>
            {forecastDone
              ? `Day ${TOTAL_FORECAST_DAYS} · Complete`
              : `${forecastDateLabel} · Day ${forecastDay}`}
          </div>
        )}
      </div>

      {/* ── Legend ───────────────────────────────────────────────────────── */}
      {signals.length > 0 && (
        <div className="map-legend" aria-label="Map legend">
          {(
            ["closure_full","closure_multi_lane","closure_single_lane",
             "demolition","construction","light_permit"] as const
          )
            .filter((t) => signals.some((s) => s.impact_type === t))
            .map((t) => (
              <span key={t} className="map-legend-item">
                <span className="map-legend-dot" style={{ background: impactColor(t) }} />
                {impactLabel(t)}
              </span>
            ))}
        </div>
      )}
    </>
  );
}
