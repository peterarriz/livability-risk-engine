"use client";

import { useEffect, useRef } from "react";

import type { NearbySignal } from "@/lib/api";

type MapViewProps = {
  latitude: number;
  longitude: number;
  address: string;
  signals?: NearbySignal[];
};

// ─── Heat colour by impact type ───────────────────────────────────────────────
// Colors chosen to be visually distinct and intuitively match severity.
const IMPACT_COLOR: Record<string, string> = {
  closure_full:        "#ff3b30",   // bright red   — highest disruption
  closure_multi_lane:  "#ff6b35",   // orange-red
  closure_single_lane: "#ff9f0a",   // amber
  demolition:          "#bf5af2",   // purple       — visually distinct
  construction:        "#ffd60a",   // yellow
  light_permit:        "#30d158",   // green        — lowest disruption
};

const DEFAULT_COLOR = "#8da5ff"; // brand blue for unknown types

// ─── Visual radius (meters) by impact type ────────────────────────────────────
const IMPACT_RADIUS: Record<string, number> = {
  closure_full:        90,
  closure_multi_lane:  75,
  closure_single_lane: 55,
  demolition:          65,
  construction:        50,
  light_permit:        38,
};
const DEFAULT_RADIUS = 45;

// Plain-language labels for popup display.
const IMPACT_LABEL: Record<string, string> = {
  closure_full:        "Full street closure",
  closure_multi_lane:  "Multi-lane closure",
  closure_single_lane: "Lane / curb closure",
  demolition:          "Demolition / excavation",
  construction:        "Active construction",
  light_permit:        "Permitted work",
};

function impactLabel(impact_type: string): string {
  return IMPACT_LABEL[impact_type] ?? impact_type;
}

function impactColor(impact_type: string): string {
  return IMPACT_COLOR[impact_type] ?? DEFAULT_COLOR;
}

function impactRadius(impact_type: string): number {
  return IMPACT_RADIUS[impact_type] ?? DEFAULT_RADIUS;
}

// Weight is a 0–45 range score contribution; map to 0.2–0.72 fill opacity.
function signalOpacity(weight: number): number {
  const maxWeight = 45;
  return Math.min(0.72, Math.max(0.2, (weight / maxWeight) * 0.72));
}

function metersToFeet(m: number): number {
  return Math.round(m * 3.28084);
}

export function MapView({ latitude, longitude, address, signals = [] }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<unknown>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    if (mapRef.current) {
      (mapRef.current as { remove(): void }).remove();
      mapRef.current = null;
    }

    // Leaflet requires window access — import dynamically to stay SSR-safe.
    import("leaflet").then((L) => {
      if (!containerRef.current) return;

      // Fix default icon URLs broken by webpack asset hashing.
      const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images/";
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconUrl: `${iconBase}marker-icon.png`,
        iconRetinaUrl: `${iconBase}marker-icon-2x.png`,
        shadowUrl: `${iconBase}marker-shadow.png`,
      });

      const map = L.map(containerRef.current).setView([latitude, longitude], 15);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      // ── Heat circles for nearby permit/closure signals ───────────────────
      const maxWeight = Math.max(...signals.map((s) => s.weight), 1);
      for (const signal of signals) {
        const color = impactColor(signal.impact_type);
        const radius = impactRadius(signal.impact_type);
        const fillOpacity = signalOpacity(signal.weight / maxWeight * 45);

        const circle = L.circle([signal.lat, signal.lon], {
          radius,
          color,
          fillColor: color,
          fillOpacity,
          weight: 1.5,
          opacity: 0.72,
        });

        const distFt = metersToFeet(signal.distance_m);
        const label = impactLabel(signal.impact_type);
        const popupHtml = `
          <div style="font-family:system-ui,sans-serif;min-width:180px">
            <div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:${color};margin-bottom:4px">${label}</div>
            <div style="font-size:0.88rem;font-weight:600;line-height:1.4;margin-bottom:6px">${signal.title}</div>
            <div style="font-size:0.75rem;color:#888">~${distFt} ft from address · ${signal.severity_hint} severity</div>
          </div>
        `;

        circle.bindPopup(popupHtml).addTo(map);
      }

      // ── Query-address marker (rendered on top of heat circles) ───────────
      L.marker([latitude, longitude]).addTo(map).bindPopup(address).openPopup();

      mapRef.current = map;
    });

    return () => {
      if (mapRef.current) {
        (mapRef.current as { remove(): void }).remove();
        mapRef.current = null;
      }
    };
  }, [latitude, longitude, address, signals]);

  return (
    <>
      {/* Leaflet CSS loaded inline to avoid adding a global import */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div
        ref={containerRef}
        style={{ height: "320px", width: "100%", borderRadius: "var(--radius, 6px)" }}
        aria-label={`Map showing location of ${address} with ${signals.length} nearby disruption signal${signals.length !== 1 ? "s" : ""}`}
      />
      {signals.length > 0 && (
        <div className="map-legend" aria-label="Map legend">
          {(["closure_full", "closure_multi_lane", "closure_single_lane", "demolition", "construction", "light_permit"] as const)
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
