export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH";
export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";

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
  // app-019: backend mode metadata — added without breaking existing consumers
  mode?: "live" | "demo";
  fallback_reason?: string | null;
};

export type ScoreSource = "live" | "demo";

type FrontendFallbackReason =
  | "frontend_api_not_configured"
  | "frontend_network_error"
  | "frontend_backend_error"
  | "frontend_invalid_response";

export type ScoreResult = {
  note?: string;
  score: ScoreResponse;
  source: ScoreSource;
};

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

  if (!apiBaseUrl) {
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_api_not_configured",
        "Demo scenario shown because the backend URL is not configured.",
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
        "Demo scenario shown because live scoring is temporarily unavailable.",
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
          ? "Demo scenario shown because the scoring service is temporarily unavailable."
          : "Demo scenario shown because the requested score could not be fetched.",
      ),
    };
  }

  try {
    const score = (await response.json()) as ScoreResponse;
    if (score.fallback_reason) {
      console.log("[LRE] backend fallback_reason:", score.fallback_reason);
    }
    return { score, source: score.mode ?? "live" };
  } catch {
    return {
      score: buildDemoScore(address),
      source: "demo",
      note: logFrontendFallback(
        "frontend_invalid_response",
        "Demo scenario shown because the scoring service returned an invalid response.",
      ),
    };
  }
}
