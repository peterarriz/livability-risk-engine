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

export type ScoreSource = "live";

export type ScoreResult = {
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

export async function fetchScore(address: string): Promise<ScoreResult> {
  const apiBaseUrl = getApiBaseUrl();

  if (!apiBaseUrl) {
    throw new ApiError("Backend URL is not configured (NEXT_PUBLIC_API_URL is unset).");
  }

  const url = buildApiUrl("/score");
  url.searchParams.set("address", address);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError("Live scoring is temporarily unavailable.");
  }

  if (!response.ok) {
    throw new ApiError(
      response.status >= 500
        ? "The scoring service is temporarily unavailable."
        : "The requested score could not be fetched.",
    );
  }

  const score = (await response.json()) as ScoreResponse;
  return { score, source: "live" };
}
