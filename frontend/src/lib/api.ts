export type ScoreProject = {
  project_id: string;
  title: string;
  impact_type: string;
  distance_m: number;
  severity: number;
  start_date: string;
  end_date: string;
  notes: string;
};

export type ScoreResponse = {
  address: string;
  location: { lat: number; lon: number };
  score: number;
  confidence: string;
  as_of: string;
  projects: ScoreProject[];
  explanation: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function fetchScore(address: string): Promise<ScoreResponse> {
  const url = new URL("/score", API_BASE_URL);
  url.searchParams.set("address", address);

  const response = await fetch(url.toString(), {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Score request failed with status ${response.status}`);
  }

  return (await response.json()) as ScoreResponse;
}
