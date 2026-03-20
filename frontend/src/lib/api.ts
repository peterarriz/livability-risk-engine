export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH";
export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";
export type ScoreMode = "live" | "demo";

// Structured metadata for a single top-risk contributor (data-024).
// Parallel to the plain-English top_risks strings but machine-readable,
// allowing the frontend to render permit IDs, dates, and source links.
export type TopRiskDetail = {
  project_id: string;
  source: string;
  source_id: string;
  title: string;
  impact_type: string;
  distance_m: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
  address: string | null;
};

export type ImpactType =
  | "closure_full"
  | "closure_multi_lane"
  | "closure_single_lane"
  | "demolition"
  | "construction"
  | "light_permit";

export type NearbySignal = {
  lat: number;
  lon: number;
  impact_type: ImpactType;
  title: string;
  impact_type: string;
  distance_m: number;
  severity_hint: string;
  weight: number;
};

export type ScoreResponse = {
  address: string;
  disruption_score: number;
  confidence: ConfidenceLevel;
  severity: {
    noise: SeverityLevel;
    traffic: SeverityLevel;
    dust: SeverityLevel;
  };
  top_risks: string[];
  explanation: string;
  // Structured per-risk metadata added in data-024. Optional for backward
  // compatibility with backend builds that predate this field.
  top_risk_details?: TopRiskDetail[];
  // Optional for backward compatibility with older backend builds.
  mode?: ScoreMode;
  fallback_reason?: string | null;
  // Coordinates returned by the backend for map display.
  latitude?: number | null;
  longitude?: number | null;
  // Nearby permit/closure signals for the map heat layer.
  nearby_signals?: NearbySignal[];
};

export type ScoreSource = ScoreMode;

type FrontendFallbackReason =
  | "frontend_api_not_configured"
  | "frontend_network_error"
  | "frontend_backend_error"
  | "frontend_invalid_response";

type LiveScoreResult = {
  score: ScoreResponse;
  source: "live";
  note?: undefined;
};

type DemoScoreResult = {
  score: ScoreResponse;
  source: "demo";
  // Optional because backend 200 demo responses do not add a note,
  // while frontend-fabricated demo fallbacks do.
  note?: string;
};

export type ScoreResult = LiveScoreResult | DemoScoreResult;

const LOCAL_API_URL = "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function getApiBaseUrl(): string {
  const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

  if (configuredApiUrl) {
    return configuredApiUrl;
  }

  if (process.env.NODE_ENV !== "production") {
    return LOCAL_API_URL;
  }

  return "";
}

function buildApiUrl(pathname: string): URL {
  return new URL(pathname, getApiBaseUrl());
}

function logFrontendFallback(reason: FrontendFallbackReason, message: string) {
  console.warn(`[LRE] frontend demo fallback: ${reason}`);
  return message;
}

// Canonical demo payload used in two places:
// 1. the backend's own demo mode when live scoring is unavailable
// 2. the frontend's fabricated fallback when it cannot reach the backend at all
function buildDemoScore(address: string): ScoreResponse {
  return {
    address,
    disruption_score: 62,
    confidence: "MEDIUM",
    severity: {
      noise: "LOW",
      traffic: "HIGH",
      dust: "LOW",
    },
    top_risks: [
      "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
      "Active closure window runs through 2026-03-22",
      "Traffic is the dominant near-term disruption signal at this address",
    ],
    top_risk_details: [],
    explanation:
      "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic disruption even though noise and dust are limited.",
    mode: "demo",
    fallback_reason: null,
    // Include coordinates for the demo address so the map pin shows immediately.
    latitude: KNOWN_COORDS[address]?.lat ?? null,
    longitude: KNOWN_COORDS[address]?.lon ?? null,
    // Demo heat signals near 1600 W Chicago Ave for map visualisation.
    nearby_signals: [
      {
        lat: 41.8959, lon: -87.6594,
        impact_type: "closure_multi_lane",
        title: "W Chicago Ave 2-lane eastbound closure",
        distance_m: 120, severity_hint: "HIGH", weight: 30.4,
      },
      {
        lat: 41.8962, lon: -87.6618,
        impact_type: "construction",
        title: "Active construction permit at 1550 W Chicago Ave",
        distance_m: 210, severity_hint: "MEDIUM", weight: 8.8,
      },
      {
        lat: 41.8948, lon: -87.6602,
        impact_type: "closure_single_lane",
        title: "Curb lane closure on S Ashland Ave",
        distance_m: 380, severity_hint: "MEDIUM", weight: 5.3,
      },
    ],
  };
}

// Pre-resolved coordinates for the canonical demo/example addresses.
// These are used as an instant fallback when Nominatim is unavailable or slow.
const KNOWN_COORDS: Record<string, { lat: number; lon: number }> = {
  "1600 W Chicago Ave, Chicago, IL": { lat: 41.8956, lon: -87.6606 },
  "700 W Grand Ave, Chicago, IL": { lat: 41.8910, lon: -87.6462 },
  "233 S Wacker Dr, Chicago, IL": { lat: 41.8788, lon: -87.6359 },
};

/**
 * Geocode an address for map display.
 * Checks a local table of known coordinates first (instant, no network).
 * Falls back to Nominatim for arbitrary addresses when a live backend is configured.
 */
export async function geocodeForMap(address: string): Promise<{ lat: number; lon: number } | null> {
  // Fast path: pre-resolved coordinates for demo/example addresses.
  const known = KNOWN_COORDS[address];
  if (known) return known;

  // 1. Live geocoding via Nominatim.
  try {
    const url = new URL("https://nominatim.openstreetmap.org/search");
    url.searchParams.set("q", address);
    url.searchParams.set("format", "json");
    url.searchParams.set("limit", "1");
    url.searchParams.set("countrycodes", "us");
    url.searchParams.set("bounded", "1");
    url.searchParams.set("viewbox", _NOMINATIM_VIEWBOX);
    const resp = await fetch(url.toString(), {
      headers: { "User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)" },
      cache: "no-store",
    });
    if (resp.ok) {
      const data = (await resp.json()) as Array<{ lat: string; lon: string }>;
      if (data.length) {
        const lat = parseFloat(data[0].lat);
        const lon = parseFloat(data[0].lon);
        if (_inChicago(lat, lon)) return { lat, lon };
      }
    }
  } catch { /* fall through */ }

  // 2. Photon fallback.
  try {
    const photonQ = address.toLowerCase().includes("chicago") ? address : `${address} Chicago`;
    const url = new URL("https://photon.komoot.io/api/");
    url.searchParams.set("q", photonQ);
    url.searchParams.set("limit", "1");
    url.searchParams.set("bbox", _PHOTON_BBOX);
    url.searchParams.set("lang", "en");
    const resp = await fetch(url.toString(), { cache: "no-store" });
    if (resp.ok) {
      const data = (await resp.json()) as { features: PhotonFeature[] };
      const f = data.features?.[0];
      if (f) {
        const [lon, lat] = f.geometry.coordinates;
        if (_inChicago(lat, lon)) return { lat, lon };
      }
    }
  } catch { /* */ }

  return null;
}

// Chicago bounding box constants shared by both geocoder calls below.
// Nominatim viewbox: left,top,right,bottom = minLon,maxLat,maxLon,minLat
const _NOMINATIM_VIEWBOX = "-87.9401,42.0230,-87.5240,41.6445";
// Photon bbox: minLon,minLat,maxLon,maxLat
const _PHOTON_BBOX = "-87.9401,41.6445,-87.5240,42.0230";
const _CHI_LAT: [number, number] = [41.6445, 42.0230];
const _CHI_LON: [number, number] = [-87.9401, -87.5240];

function _inChicago(lat: number, lon: number): boolean {
  return lat >= _CHI_LAT[0] && lat <= _CHI_LAT[1] && lon >= _CHI_LON[0] && lon <= _CHI_LON[1];
}

type NominatimItem = {
  lat: string;
  lon: string;
  address: { house_number?: string; road?: string; pedestrian?: string; highway?: string };
};

type PhotonFeature = {
  geometry: { coordinates: [number, number] };
  properties: { countrycode?: string; housenumber?: string; street?: string };
};

function _parseNominatim(items: NominatimItem[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of items) {
    const lat = parseFloat(r.lat), lon = parseFloat(r.lon);
    if (!_inChicago(lat, lon)) continue;
    const a = r.address;
    const road = a.road ?? a.pedestrian ?? a.highway ?? "";
    if (!road) continue;
    const house = a.house_number ?? "";
    const s = house ? `${house} ${road}, Chicago, IL` : `${road}, Chicago, IL`;
    if (!seen.has(s)) { seen.add(s); out.push(s); }
  }
  return out.slice(0, 5);
}

function _parsePhoton(features: PhotonFeature[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const f of features) {
    if (f.properties.countrycode?.toUpperCase() !== "US") continue;
    const [lon, lat] = f.geometry.coordinates;
    if (!_inChicago(lat, lon)) continue;
    const street = f.properties.street ?? "";
    if (!street) continue;
    const house = f.properties.housenumber ?? "";
    const s = house ? `${house} ${street}, Chicago, IL` : `${street}, Chicago, IL`;
    if (!seen.has(s)) { seen.add(s); out.push(s); }
  }
  return out.slice(0, 5);
}

/**
 * Fetch address suggestions for a partial query.
 *
 * Strategy (in order):
 *  1. Backend /suggest  — server-side Nominatim → Photon; best in production
 *  2. Browser Nominatim — direct from user's browser; bypasses server proxy limits
 *  3. Browser Photon    — fallback if Nominatim is also unreachable from browser
 */
export async function fetchSuggestions(query: string): Promise<string[]> {
  const q = query.trim();
  if (q.length < 3) return [];

  // 1. Backend endpoint (tries Nominatim then Photon server-side).
  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    try {
      const url = buildApiUrl("/suggest");
      url.searchParams.set("q", q);
      const resp = await fetch(url.toString(), { cache: "no-store" });
      if (resp.ok) {
        const data = (await resp.json()) as { suggestions: string[] };
        if (data.suggestions?.length) return data.suggestions;
      }
    } catch {
      // Backend unreachable — fall through to browser-side geocoding.
    }
  }

  const biasedQ = q.toLowerCase().includes("chicago") ? q : `${q}, Chicago, IL`;

  // 2. Browser-side Nominatim.
  try {
    const url = new URL("https://nominatim.openstreetmap.org/search");
    url.searchParams.set("q", biasedQ);
    url.searchParams.set("format", "json");
    url.searchParams.set("limit", "8");
    url.searchParams.set("countrycodes", "us");
    url.searchParams.set("bounded", "1");
    url.searchParams.set("viewbox", _NOMINATIM_VIEWBOX);
    url.searchParams.set("addressdetails", "1");
    const resp = await fetch(url.toString(), {
      headers: { "User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)" },
      cache: "no-store",
    });
    if (resp.ok) {
      const suggestions = _parseNominatim((await resp.json()) as NominatimItem[]);
      if (suggestions.length) return suggestions;
    }
  } catch { /* fall through */ }

  // 3. Browser-side Photon fallback.
  try {
    const photonQ = q.toLowerCase().includes("chicago") ? q : `${q} Chicago`;
    const url = new URL("https://photon.komoot.io/api/");
    url.searchParams.set("q", photonQ);
    url.searchParams.set("limit", "8");
    url.searchParams.set("bbox", _PHOTON_BBOX);
    url.searchParams.set("lang", "en");
    const resp = await fetch(url.toString(), { cache: "no-store" });
    if (resp.ok) {
      return _parsePhoton(((await resp.json()) as { features: PhotonFeature[] }).features ?? []);
    }
  } catch { /* */ }

  return [];
}

/**
 * Build a URL for the export endpoints (/export/csv or /export/pdf).
 * Returns an empty string if the backend is not configured.
 */
export function getExportUrl(type: "csv" | "pdf", address: string): string {
  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) return "";
  const url = buildApiUrl(`/export/${type}`);
  url.searchParams.set("address", address);
  return url.toString();
}

export type SaveReportResponse = {
  report_id: string;
};

export type FetchReportResponse = ScoreResponse & {
  report_id: string;
  created_at: string;
};

/**
 * Save a score result to the backend and return a shareable report_id.
 * Throws ApiError if the backend is unreachable or DB is not configured.
 */
export async function saveReport(score: ScoreResponse): Promise<SaveReportResponse> {
  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) {
    throw new ApiError("Backend not configured. Cannot save report.");
  }
  const url = buildApiUrl("/save-report");
  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(score),
  });
  if (!resp.ok) {
    throw new ApiError(`Save failed: ${resp.status}`);
  }
  return (await resp.json()) as SaveReportResponse;
}

/**
 * Fetch a previously saved report by its UUID.
 * Returns null when not found or the backend is unreachable.
 */
export async function fetchReport(reportId: string): Promise<FetchReportResponse | null> {
  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) return null;
  try {
    const url = buildApiUrl(`/report/${reportId}`);
    const resp = await fetch(url.toString(), { cache: "no-store" });
    if (!resp.ok) return null;
    return (await resp.json()) as FetchReportResponse;
  } catch {
    return null;
  }
}

export type HistoryEntry = {
  disruption_score: number;
  confidence: ConfidenceLevel;
  mode: string;
  scored_at: string;
};

export type HistoryResponse = {
  address: string;
  history: HistoryEntry[];
};

/**
 * Fetch recent score history for a given address.
 * Returns null when the backend is unreachable or not configured.
 * Returns an empty history array when DB is in demo mode.
 */
export async function fetchHistory(
  address: string,
  limit = 10,
): Promise<HistoryResponse | null> {
  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) return null;

  try {
    const url = buildApiUrl("/history");
    url.searchParams.set("address", address);
    url.searchParams.set("limit", String(limit));
    const resp = await fetch(url.toString(), { cache: "no-store" });
    if (!resp.ok) return null;
    return (await resp.json()) as HistoryResponse;
  } catch {
    return null;
  }
}

export async function fetchScore(address: string): Promise<ScoreResult> {
  const apiBaseUrl = getApiBaseUrl();

  // No backend URL — throw so the caller surfaces a clear error rather than
  // silently showing demo data the user didn't ask for.
  if (!apiBaseUrl) {
    logFrontendFallback("frontend_api_not_configured", "NEXT_PUBLIC_API_URL not set");
    throw new ApiError(
      "Backend URL is not configured. Set NEXT_PUBLIC_API_URL to enable live scoring.",
    );
  }

  const url = buildApiUrl("/score");
  url.searchParams.set("address", address);

  let response: Response;
  try {
    response = await fetch(url.toString(), { cache: "no-store" });
  } catch (err) {
    logFrontendFallback("frontend_network_error", String(err));
    throw new ApiError(
      "Could not reach the scoring backend. Check your connection or try again in a moment.",
    );
  }

  if (!response.ok) {
    console.warn(`[LRE] backend score request failed: status=${response.status}`);
    if (response.status === 404) {
      throw new ApiError("Address not found. Try including a ZIP code or nearby intersection.");
    }
    throw new ApiError(
      response.status >= 500
        ? "The scoring service returned an error. Try again in a moment."
        : `Scoring request failed (${response.status}).`,
    );
  }

  const score = (await response.json()) as ScoreResponse;
  if (score.fallback_reason) {
    console.log("[LRE] backend fallback_reason:", score.fallback_reason);
  }

  // When the backend explicitly marks this as demo, pass that through.
  // This is the backend's intentional decision (e.g. DB not yet configured).
  const source: ScoreSource = score.mode ?? "live";
  if (source === "demo") {
    return {
      score,
      source: "demo",
      note: score.fallback_reason === "db_not_configured"
        ? "Backend is live but the database is not yet connected — showing sample data."
        : undefined,
    };
  }
  return { score, source: "live" };
}
