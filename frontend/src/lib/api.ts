export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH";
export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";
export type ScoreMode = "live" | "demo";

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
  // Optional for backward compatibility with older backend builds.
  mode?: ScoreMode;
  fallback_reason?: string | null;
  // Coordinates returned by the backend for map display.
  latitude?: number | null;
  longitude?: number | null;
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
    explanation:
      "A nearby 2-lane closure is the main driver, so this address has elevated short-term traffic disruption even though noise and dust are limited.",
    mode: "demo",
    fallback_reason: null,
    // Include coordinates for the demo address so the map pin shows immediately.
    latitude: KNOWN_COORDS[address]?.lat ?? null,
    longitude: KNOWN_COORDS[address]?.lon ?? null,
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

  // Live geocoding via Nominatim (works in production; may be blocked in restricted envs).
  try {
    const url = new URL("https://nominatim.openstreetmap.org/search");
    url.searchParams.set("q", address);
    url.searchParams.set("format", "json");
    url.searchParams.set("limit", "1");
    url.searchParams.set("countrycodes", "us");
    const resp = await fetch(url.toString(), {
      headers: { "User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)" },
      cache: "no-store",
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as Array<{ lat: string; lon: string }>;
    if (!data.length) return null;
    return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
  } catch {
    return null;
  }
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

export async function fetchScore(address: string): Promise<ScoreResult> {
  const apiBaseUrl = getApiBaseUrl();

  // No backend URL means the frontend must fabricate the approved demo response.
  if (!apiBaseUrl) {
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_api_not_configured",
        "Showing the approved demo scenario while the live backend URL is being configured.",
      ),
    };
  }

  const url = buildApiUrl("/score");
  url.searchParams.set("address", address);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      cache: "no-store",
    });
  } catch {
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_network_error",
        "Showing the approved demo scenario while live scoring is temporarily unavailable.",
      ),
    };
  }

  if (!response.ok) {
    console.warn(`[LRE] backend score request failed: status=${response.status}`);
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_backend_error",
        response.status >= 500
          ? "Showing the approved demo scenario while the scoring service is temporarily unavailable."
          : "Showing the approved demo scenario because this lookup could not be completed right now.",
      ),
    };
  }

  try {
    const score = (await response.json()) as ScoreResponse;
    if (score.fallback_reason) {
      console.log("[LRE] backend fallback_reason:", score.fallback_reason);
    }

    // Historically, repeated 62s usually meant demo fallback was active somewhere.
    // Prefer the backend's explicit mode when present so a 200 demo response is not
    // mislabeled as a live result by the frontend fetch layer.
    const source: ScoreSource = score.mode ?? "live";
    if (source === "demo") {
      return { score, source: "demo" };
    }
    return { score, source: "live" };
  } catch {
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_invalid_response",
        "Showing the approved demo scenario because the scoring response could not be validated.",
      ),
    };
  }
}
