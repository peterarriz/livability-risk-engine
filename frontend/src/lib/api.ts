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
  };
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
