"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fetchMapNarration, type NearbyAmenity, type NearbySchool, type NearbySignal, type TopRiskDetail } from "@/lib/api";

type MapMode = "signals" | "heatmap";
type NarrationInteraction = "default_load" | "signal_click" | "map_pan";

type MapViewProps = {
  latitude: number;
  longitude: number;
  address: string;
  disruptionScore?: number;
  signals?: NearbySignal[];
  schools?: NearbySchool[];
  amenities?: NearbyAmenity[];
  topRiskDetails?: TopRiskDetail[];
  nearbySchools?: NearbySchool[];
  floodRisk?: string | null;
  femaZone?: string | null;
  isPro?: boolean;
};

// ─── Impact-type colour palette (per design spec) ─────────────────────────────
// Red    = access/traffic disruption (closures)
// Amber  = construction activity
// Orange = road construction (IDOT / city road works)
// Purple = utility/demolition signals
// Blue   = minor / noise / event permits
const IMPACT_COLOR: Record<string, string> = {
  closure_full:        "#EF4444", // red
  closure_multi_lane:  "#EF4444", // red
  closure_single_lane: "#EF4444", // red
  demolition:          "#8B5CF6", // purple
  construction:        "#F59E0B", // amber
  road_construction:   "#F97316", // orange
  light_permit:        "#3B82F6", // blue
  // Utility disruption signals (data-060 / data-046)
  utility_outage:        "#7C3AED", // deep violet — high severity (weight 25)
  utility_repair:        "#A78BFA", // light violet — medium severity (weight 15)
  // Traffic signal outage (data-038) — yellow: universal "signal" colour
  traffic_signal_outage: "#EAB308", // yellow (weight 22)
  // Crime trend signals (data-054)
  crime_trend_increasing: "#DC2626", // dark red — elevated risk
  crime_trend_stable:     "#6B7280", // slate gray — neutral
  crime_trend_decreasing: "#16A34A", // green — improving
};
const DEFAULT_COLOR = "#94a3b8";

// ─── School rating → colour (data-061) ────────────────────────────────────────
function schoolRatingColor(rating: string | null | undefined): string {
  if (!rating) return "#6B7280"; // gray — unknown
  const r = rating.trim().toUpperCase();
  if (r === "LEVEL 1+" || r === "EXCELLENT") return "#16A34A"; // green
  if (r === "LEVEL 1"  || r === "STRONG")    return "#4ADE80"; // light green
  if (r === "LEVEL 2"  || r === "AVERAGE")   return "#EAB308"; // yellow
  if (r === "LEVEL 3"  || r === "WEAK")      return "#F97316"; // orange
  if (r === "LEVEL 4"  || r === "VERY WEAK") return "#DC2626"; // red
  return "#6B7280"; // gray — unrecognised
}

// ─── CircleMarker pixel radius — weight-proportional, clamped 8–28px ─────────
function signalPixelRadius(weight: number): number {
  return Math.min(28, Math.max(8, 8 + (weight / 45) * 20));
}

// ─── Heatmap blob radius (meters — geographic, intentionally large) ───────────
const HEAT_RADIUS: Record<string, number> = {
  closure_full:        200,
  closure_multi_lane:  175,
  closure_single_lane: 145,
  demolition:          165,
  construction:        130,
  road_construction:   155,
  light_permit:        95,
  // Utility disruption signals (data-060 / data-046)
  utility_outage:        170,
  utility_repair:        130,
  // Traffic signal outage (data-038)
  traffic_signal_outage: 160,
  // Crime trend signals (data-054) — large radius to convey neighborhood-level scope
  crime_trend_increasing: 500,
  crime_trend_stable:     450,
  crime_trend_decreasing: 450,
};
const DEFAULT_HEAT_RADIUS = 120;

// ─── Labels ───────────────────────────────────────────────────────────────────
const IMPACT_LABEL: Record<string, string> = {
  closure_full:        "Full street closure",
  closure_multi_lane:  "Multi-lane closure",
  closure_single_lane: "Lane / curb closure",
  demolition:          "Demolition / excavation",
  construction:        "Active construction",
  road_construction:   "Road construction",
  light_permit:        "Permitted work",
  // Utility disruption signals (data-060 / data-046)
  utility_outage:        "Utility outage",
  utility_repair:        "Utility repair",
  // Traffic signal outage (data-038)
  traffic_signal_outage: "Traffic signal outage",
  // Crime trend signals (data-054)
  crime_trend_increasing: "Crime trend: increasing",
  crime_trend_stable:     "Crime trend: stable",
  crime_trend_decreasing: "Crime trend: decreasing",
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
  chicago_crime_trends:    "Chicago Crime Trends",
};

// Distance rings drawn around the searched address (meters)
const DISTANCE_RINGS = [
  { radius: 250, label: "250 m" },
  { radius: 500, label: "500 m · scoring boundary" },
];

const ALL_IMPACT_TYPES = [
  "closure_full", "closure_multi_lane", "closure_single_lane",
  "demolition", "construction", "road_construction", "light_permit",
  "utility_outage", "utility_repair", "traffic_signal_outage",
  "crime_trend_increasing", "crime_trend_stable", "crime_trend_decreasing",
] as const;

function impactLabel(t: string) { return IMPACT_LABEL[t] ?? t; }
function impactColor(t: string) { return IMPACT_COLOR[t] ?? DEFAULT_COLOR; }
function heatRadius(t: string) { return HEAT_RADIUS[t] ?? DEFAULT_HEAT_RADIUS; }
function sourceLabel(s: string) { return SOURCE_LABEL[s] ?? s; }

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
  if (start && end) return `${fmt(start)} \u2013 ${fmt(end)}`;
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
  disruptionScore,
  signals = [],
  schools = [],
  amenities = [],
  topRiskDetails: _topRiskDetails = [],
  nearbySchools = [],
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ringGroupRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const schoolGroupRef = useRef<any>(null);

  // mapVersion increments after the Leaflet async init completes, triggering
  // the layer-update effect which would otherwise see null refs.
  const [mapVersion, setMapVersion] = useState(0);
  const [mapMode, setMapMode] = useState<MapMode>("signals");
  const [forecastActive, setForecastActive] = useState(false);
  const [forecastDay, setForecastDay] = useState(0);
  const [showRings, setShowRings] = useState(true);
  const [showTransitLayer, setShowTransitLayer] = useState(true);
  const [narration, setNarration] = useState<string | null>(null);
  const [pendingNarration, setPendingNarration] = useState<{
    type: NarrationInteraction;
    clicked?: NearbySignal;
    center?: { lat: number; lon: number };
  } | null>(null);
  const narrationSeqRef = useRef(0);
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
      ringGroupRef.current = null;
      schoolGroupRef.current = null;
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
      map.on("moveend", () => {
        const center = map.getCenter();
        setPendingNarration({
          type: "map_pan",
          center: { lat: center.lat, lon: center.lng },
        });
      });

      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 20,
        subdomains: "abcd",
      }).addTo(map);

      L.marker([latitude, longitude]).addTo(map).bindPopup(address).openPopup();

      // Distance rings (250 m inner + 500 m scoring boundary)
      const ringGroup = L.layerGroup();
      for (const ring of DISTANCE_RINGS) {
        L.circle([latitude, longitude], {
          radius: ring.radius,
          color: "rgba(148,163,184,0.4)",
          weight: 1,
          dashArray: "5 6",
          fillOpacity: 0,
        }).bindTooltip(ring.label, { sticky: true, direction: "top" })
          .addTo(ringGroup);
      }
      ringGroupRef.current = ringGroup;
      ringGroup.addTo(map); // visible by default

      signalGroupRef.current = L.layerGroup().addTo(map);
      heatGroupRef.current   = L.layerGroup(); // added/removed by layer effect
      schoolGroupRef.current = L.layerGroup().addTo(map); // school markers always visible
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
        ringGroupRef.current = null;
        schoolGroupRef.current = null;
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

    const filteredSignals = showTransitLayer
      ? signals
      : signals.filter((s) => !(s.source || "").startsWith("cta"));

    const active = forecastActive
      ? filteredSignals.filter((s) => isSignalActiveOnDay(s, forecastDate))
      : filteredSignals;
    const faded = forecastActive
      ? filteredSignals.filter((s) => !isSignalActiveOnDay(s, forecastDate))
      : [];

    // ── Debug: log signals to console so devtools can confirm data is present ──
    console.debug(
      "[MapView] rendering signals mode=%s active=%d faded=%d total=%d",
      mapMode, active.length, faded.length, filteredSignals.length,
      active.slice(0, 3).map((s) => ({ lat: s.lat, lon: s.lon, type: s.impact_type, weight: s.weight })),
    );

    if (mapMode === "signals") {
      // ── Signal-circles mode — L.circleMarker (fixed pixel radius) ────────
      for (const s of active) {
        const color  = impactColor(s.impact_type);
        // Crime trend signals have weight=0 (context-only); give them a fixed
        // dashed outline so they're clearly distinct from disruption circles.
        const isCrimeTrend = s.impact_type.startsWith("crime_trend_");
        const radius = isCrimeTrend ? 18 : signalPixelRadius(s.weight);
        const distFt = metersToFeet(s.distance_m);
        const src    = s.source ? sourceLabel(s.source) : "City of Chicago";
        const dates  = formatDateRange(s.start_date, s.end_date);

        // Clean title: strip raw permit IDs (anything starting with "permit_"
        // or ending with a long hex/numeric suffix) so popups read naturally.
        const cleanTitle = s.title.replace(/\s*\(permit_\S+\)/gi, "").trim();

        const popup = `
          <div style="font-family:system-ui,sans-serif;min-width:200px;max-width:240px;padding:2px 0">
            <div style="font-size:0.65rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:${color};margin-bottom:5px">${impactLabel(s.impact_type)}</div>
            <div style="font-size:0.85rem;font-weight:600;line-height:1.35;margin-bottom:8px;color:#f1f5f9">${cleanTitle}</div>
            <table style="font-size:0.72rem;color:#94a3b8;border-collapse:collapse;width:100%">
              <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Distance</td><td>~${distFt.toLocaleString()} ft away</td></tr>
              <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Active</td><td>${dates}</td></tr>
              <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Source</td><td>${src}</td></tr>
            </table>
          </div>`;

        L.circleMarker([s.lat, s.lon], {
          radius,
          color: isCrimeTrend ? color : "#ffffff",
          weight: isCrimeTrend ? 2 : 1,
          dashArray: isCrimeTrend ? "4 3" : undefined,
          fillColor: color,
          fillOpacity: isCrimeTrend ? 0.12 : 0.7,
          opacity: isCrimeTrend ? 0.8 : 0.9,
        }).bindPopup(popup, { maxWidth: 260 })
          .on("click", () => setPendingNarration({ type: "signal_click", clicked: s }))
          .addTo(signalGroup);
      }

      // Faded (out-of-window) signals shown as ghost outlines.
      for (const s of faded) {
        const color = impactColor(s.impact_type);
        L.circleMarker([s.lat, s.lon], {
          radius: signalPixelRadius(s.weight),
          color,
          weight: 1,
          fillColor: color,
          fillOpacity: 0.12,
          opacity: 0.25,
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
  }, [mapVersion, signals, mapMode, forecastDay, forecastActive, showTransitLayer]);

  // ── Effect 3: School quality markers (data-061) ───────────────────────────
  useEffect(() => {
    const L = leafletRef.current;
    const schoolGroup = schoolGroupRef.current;
    if (!L || !schoolGroup) return;

    schoolGroup.clearLayers();

    for (const school of schools) {
      const hex = schoolRatingColor(school.rating);
      const rating = school.rating ?? "Unknown";
      const distFt = metersToFeet(school.distance_m);
      const popup = `
        <div style="font-family:system-ui,sans-serif;min-width:180px;max-width:220px;padding:2px 0">
          <div style="font-size:0.65rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:${hex};margin-bottom:5px">School</div>
          <div style="font-size:0.85rem;font-weight:600;line-height:1.35;margin-bottom:8px;color:#f1f5f9">${school.name}</div>
          <table style="font-size:0.72rem;color:#94a3b8;border-collapse:collapse;width:100%">
            <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Rating</td><td>${rating}</td></tr>
            <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Distance</td><td>~${distFt.toLocaleString()} ft away</td></tr>
          </table>
        </div>`;

      L.circleMarker([school.lat, school.lon], {
        radius: 7,
        color: hex,
        weight: 2,
        fillColor: hex,
        fillOpacity: 0.5,
        opacity: 0.9,
      }).bindPopup(popup, { maxWidth: 240 }).addTo(schoolGroup);
    }
  }, [mapVersion, schools]);

  // ── Effect 5: Start / stop forecast animation ─────────────────────────────
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

  // ── Effect 6: Auto-stop when animation completes ──────────────────────────
  useEffect(() => {
    if (forecastDay >= TOTAL_FORECAST_DAYS && forecastTimerRef.current) {
      clearInterval(forecastTimerRef.current);
      forecastTimerRef.current = null;
    }
  }, [forecastDay]);

  // ── Effect 7: Show / hide distance rings ─────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    const ringGroup = ringGroupRef.current;
    if (!map || !ringGroup) return;
    if (showRings) {
      if (!map.hasLayer(ringGroup)) ringGroup.addTo(map);
    } else {
      if (map.hasLayer(ringGroup)) map.removeLayer(ringGroup);
    }
  }, [showRings, mapVersion]);

  // ── Effect 6: Render school quality markers ───────────────────────────────
  useEffect(() => {
    const L = leafletRef.current;
    const schoolGroup = schoolGroupRef.current;
    if (!L || !schoolGroup) return;

    schoolGroup.clearLayers();

    for (const school of nearbySchools) {
      const color = schoolRatingColor(school.rating);
      const distFt = metersToFeet(school.distance_m);
      const ratingLabel = school.rating ?? "Unknown";

      const popup = `
        <div style="font-family:system-ui,sans-serif;min-width:200px;max-width:240px;padding:2px 0">
          <div style="font-size:0.65rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:${color};margin-bottom:5px">School</div>
          <div style="font-size:0.85rem;font-weight:600;line-height:1.35;margin-bottom:8px;color:#f1f5f9">${school.name}</div>
          <table style="font-size:0.72rem;color:#94a3b8;border-collapse:collapse;width:100%">
            <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Rating</td><td>${ratingLabel}</td></tr>
            <tr><td style="padding:2px 8px 2px 0;white-space:nowrap;color:#cbd5e1">Distance</td><td>~${distFt.toLocaleString()} ft away</td></tr>
          </table>
        </div>`;

      // Square school marker via divIcon to distinguish from signal circles
      const icon = L.divIcon({
        className: "",
        html: `<div style="
          width:12px;height:12px;
          background:${color};
          border:2px solid rgba(255,255,255,0.85);
          border-radius:2px;
          opacity:0.9;
        "></div>`,
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      });

      L.marker([school.lat, school.lon], { icon })
        .bindPopup(popup, { maxWidth: 260 })
        .addTo(schoolGroup);
    }
  }, [mapVersion, nearbySchools]);

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
      ? `\u2713 Done \u2014 click to replay`
      : `\u25fc Stop  \u00b7  ${forecastDateLabel}`
    : "\u25b6 30-day forecast";

  // ── Signal counts per type (for legend badges) ────────────────────────────
  const displayedSignals = useMemo(
    () => (
      showTransitLayer
        ? signals
        : signals.filter((s) => !(s.source || "").startsWith("cta"))
    ),
    [signals, showTransitLayer],
  );

  const typeCounts: Record<string, number> = {};
  for (const s of displayedSignals) {
    typeCounts[s.impact_type] = (typeCounts[s.impact_type] ?? 0) + 1;
  }

  // Trigger default narration when signal set changes (including transit toggle).
  useEffect(() => {
    if (displayedSignals.length === 0) {
      setNarration(null);
      setPendingNarration(null);
      return;
    }
    setPendingNarration({ type: "default_load" });
  }, [address, displayedSignals.length]);

  // Debounced narrator updates (800ms after interaction).
  useEffect(() => {
    if (!pendingNarration || displayedSignals.length === 0) return;
    const timer = setTimeout(async () => {
      const seq = ++narrationSeqRef.current;
      const response = await fetchMapNarration({
        address,
        interaction_type: pendingNarration.type,
        signals: displayedSignals,
        top_signal_title: displayedSignals[0]?.title,
        clicked_signal: pendingNarration.clicked,
        original_score: Math.round(
          disruptionScore ?? displayedSignals.reduce((sum, s) => sum + (s.weight || 0), 0),
        ),
        current_lat: pendingNarration.center?.lat,
        current_lon: pendingNarration.center?.lon,
      });
      if (seq !== narrationSeqRef.current) return;
      setNarration(response.narration);
    }, 800);
    return () => clearTimeout(timer);
  }, [pendingNarration, address, displayedSignals]);

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

        {/* Distance rings toggle */}
        <button
          type="button"
          onClick={() => setShowRings((v) => !v)}
          aria-pressed={showRings}
          title="Toggle 250 m / 500 m distance rings"
          style={{
            padding: "5px 13px",
            fontSize: "0.74rem",
            fontWeight: 600,
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "7px",
            cursor: "pointer",
            background: showRings ? "rgba(148,163,184,0.15)" : "rgba(255,255,255,0.04)",
            color: showRings ? "#cbd5e1" : "var(--text-muted, #94a3b8)",
            transition: "background 0.14s, color 0.14s",
            whiteSpace: "nowrap",
          }}
        >
          &#8857; Rings
        </button>

        {/* CTA transit layer toggle */}
        <button
          type="button"
          onClick={() => setShowTransitLayer((v) => !v)}
          aria-pressed={showTransitLayer}
          title="Toggle CTA service alert signals"
          style={{
            padding: "5px 13px",
            fontSize: "0.74rem",
            fontWeight: 600,
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "7px",
            cursor: "pointer",
            background: showTransitLayer ? "rgba(96,165,250,0.2)" : "rgba(255,255,255,0.04)",
            color: showTransitLayer ? "#bfdbfe" : "var(--text-muted, #94a3b8)",
            transition: "background 0.14s, color 0.14s",
            whiteSpace: "nowrap",
          }}
        >
          {showTransitLayer ? "🚇 Transit on" : "🚇 Transit off"}
        </button>

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
            Upgrade &rarr;
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

      {/* Claude narrator panel (hidden if unavailable) */}
      {narration && (
        <div style={{
          marginBottom: "10px",
          padding: "10px 12px",
          borderRadius: "8px",
          border: "1px solid rgba(125,211,252,0.25)",
          background: "rgba(14,116,144,0.14)",
          color: "#dbeafe",
          fontSize: "0.8rem",
          lineHeight: 1.45,
        }}>
          <div style={{
            fontSize: "0.65rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontWeight: 700,
            color: "#7dd3fc",
            marginBottom: "4px",
          }}>
            Live area narrator
          </div>
          {narration}
        </div>
      )}

      {/* ── Forecast scrubber — Pro only, shown when forecast is active ───── */}
      {isPro && forecastActive && (
        <div style={{
          display: "flex", alignItems: "center", gap: "10px",
          marginBottom: "8px", padding: "6px 10px",
          background: "rgba(124,58,237,0.12)",
          borderRadius: "6px",
          border: "1px solid rgba(124,58,237,0.25)",
        }}>
          <span style={{ fontSize: "0.72rem", color: "#a78bfa", fontWeight: 600, whiteSpace: "nowrap" }}>
            Day {forecastDay}
          </span>
          <input
            type="range"
            min={0}
            max={TOTAL_FORECAST_DAYS}
            value={forecastDay}
            onChange={(e) => {
              // Pause auto-play when user scrubs manually
              if (forecastTimerRef.current) {
                clearInterval(forecastTimerRef.current);
                forecastTimerRef.current = null;
              }
              setForecastDay(Number(e.target.value));
            }}
            style={{ flex: 1, accentColor: "#7c3aed", cursor: "pointer" }}
            aria-label="Forecast day scrubber"
          />
          <span style={{ fontSize: "0.72rem", color: "#a78bfa", fontWeight: 600, whiteSpace: "nowrap" }}>
            {forecastDateLabel}
          </span>
        </div>
      )}

      {/* ── Map container ────────────────────────────────────────────────── */}
      <div style={{ position: "relative" }}>
        <div
          ref={containerRef}
          style={{ height: "420px", width: "100%", borderRadius: "var(--radius, 6px)" }}
          aria-label={`Map showing ${address} with ${displayedSignals.length} nearby signal${displayedSignals.length !== 1 ? "s" : ""}`}
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
              ? `Day ${TOTAL_FORECAST_DAYS} \u00b7 Complete`
              : `${forecastDateLabel} \u00b7 Day ${forecastDay}`}
          </div>
        )}

        {/* Distance ring key — shown in bottom-left when rings are on */}
        {showRings && (
          <div style={{
            position: "absolute", bottom: "10px", left: "10px", zIndex: 1000,
            background: "rgba(15,23,42,0.82)", color: "#94a3b8",
            padding: "5px 9px", borderRadius: "5px",
            fontSize: "0.64rem", fontWeight: 500,
            pointerEvents: "none", backdropFilter: "blur(3px)",
            display: "flex", flexDirection: "column", gap: "2px",
            lineHeight: 1.5,
          }}>
            <span>&#8729; 250 m</span>
            <span>&#8729; 500 m &nbsp;<span style={{ color: "#64748b" }}>scoring boundary</span></span>
          </div>
        )}
      </div>

      {/* ── Legend with signal counts ─────────────────────────────────────── */}
      {displayedSignals.length > 0 && (
        <div className="map-legend" aria-label="Map legend">
          {ALL_IMPACT_TYPES
            .filter((t) => displayedSignals.some((s) => s.impact_type === t))
            .map((t) => (
              <span key={t} className="map-legend-item">
                <span className="map-legend-dot" style={{ background: impactColor(t) }} />
                {impactLabel(t)}
                {typeCounts[t] != null && (
                  <span style={{
                    marginLeft: "4px",
                    fontSize: "0.62rem",
                    fontWeight: 700,
                    background: "rgba(255,255,255,0.09)",
                    borderRadius: "9px",
                    padding: "0 5px",
                    color: "#94a3b8",
                  }}>
                    {typeCounts[t]}
                  </span>
                )}
              </span>
            ))}
        </div>
      )}
    </>
  );
}
