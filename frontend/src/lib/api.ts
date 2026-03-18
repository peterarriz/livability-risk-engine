export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH";

export type ScoreResponse = {
  address: string;
  disruption_score: number;
  confidence: string;
  severity: {
    noise: SeverityLevel;
    traffic: SeverityLevel;
    dust: SeverityLevel;
  };
  top_risks: string[];
  explanation: string;
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

  throw new ApiError(
    "The app is missing its backend URL configuration. Add NEXT_PUBLIC_API_URL to connect the frontend.",
  );
}

function buildApiUrl(pathname: string): URL {
  return new URL(pathname, getApiBaseUrl());
}

export async function fetchScore(address: string): Promise<ScoreResponse> {
  const url = buildApiUrl("/score");
  url.searchParams.set("address", address);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "We couldn't reach the disruption scoring service. Please try again in a moment.",
    );
  }

  if (!response.ok) {
    throw new ApiError(
      response.status >= 500
        ? "The disruption scoring service is temporarily unavailable. Please try again soon."
        : "We couldn't fetch a disruption score for that address right now.",
    );
  }

  try {
    return (await response.json()) as ScoreResponse;
  } catch {
    throw new ApiError("The disruption scoring service returned an invalid response.");
  }
}
