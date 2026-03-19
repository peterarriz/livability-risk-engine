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

/**
 * Fetch address suggestions for a partial query.
 *
 * Strategy:
 *  1. Try the backend /suggest endpoint (server-side Nominatim call).
 *  2. If the backend returns empty or fails, call Nominatim directly from the
 *     browser — this bypasses server-side proxy restrictions and works in any
 *     environment where the user's browser can reach nominatim.openstreetmap.org.
 */
export async function fetchSuggestions(query: string): Promise<string[]> {
  const q = query.trim();
  if (q.length < 3) return [];

  // 1. Try backend endpoint.
  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    try {
      const url = buildApiUrl("/suggest");
      url.searchParams.set("q", q);
      const response = await fetch(url.toString(), { cache: "no-store" });
      if (response.ok) {
        const data = (await response.json()) as { suggestions: string[] };
        if (data.suggestions?.length) return data.suggestions;
      }
    } catch {
      // Backend unavailable — fall through to browser-side geocoding.
    }
  }

  // 2. Browser-side Nominatim call (works even when server cannot reach it).
  try {
    const url = new URL("https://nominatim.openstreetmap.org/search");
    const searchQuery = q.toLowerCase().includes("chicago") ? q : `${q}, Chicago, IL`;
    url.searchParams.set("q", searchQuery);
    url.searchParams.set("format", "json");
    url.searchParams.set("limit", "5");
    url.searchParams.set("countrycodes", "us");
    url.searchParams.set("viewbox", "-87.9401,41.6445,-87.5240,42.0230");
    url.searchParams.set("bounded", "1");
    url.searchParams.set("addressdetails", "1");

    const resp = await fetch(url.toString(), {
      headers: { "User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)" },
      cache: "no-store",
    });
    if (!resp.ok) return [];

    type NominatimResult = {
      address: {
        house_number?: string;
        road?: string;
        city?: string;
        town?: string;
        village?: string;
        state?: string;
      };
    };

    const data = (await resp.json()) as NominatimResult[];
    const suggestions: string[] = [];
    const seen = new Set<string>();

    for (const item of data) {
      const addr = item.address;
      const parts: string[] = [];

      const houseNumber = addr.house_number ?? "";
      const road = addr.road ?? "";
      if (houseNumber && road) parts.push(`${houseNumber} ${road}`);
      else if (road) parts.push(road);

      const city = addr.city ?? addr.town ?? addr.village ?? "";
      const state = addr.state ?? "";
      if (city && state) parts.push(`${city}, ${state}`);
      else if (city) parts.push(city);

      if (parts.length) {
        const formatted = parts.join(", ");
        if (!seen.has(formatted)) {
          seen.add(formatted);
          suggestions.push(formatted);
        }
      }
    }

    return suggestions.slice(0, 5);
  } catch {
    return [];
  }
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
