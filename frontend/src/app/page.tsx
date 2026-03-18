"use client";

import { FormEvent, useMemo, useState } from "react";

import { fetchScore, ScoreProject, ScoreResponse } from "@/lib/api";

type SeverityLevel = "LOW" | "MEDIUM" | "HIGH";

type SeverityBreakdown = {
  noise: SeverityLevel;
  traffic: SeverityLevel;
  dust: SeverityLevel;
};

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";

function levelFromScore(score: number): SeverityLevel {
  if (score >= 67) return "HIGH";
  if (score >= 34) return "MEDIUM";
  return "LOW";
}

function deriveSeverity(score: number, projects: ScoreProject[]): SeverityBreakdown {
  const overall = levelFromScore(score);
  const trafficProject = projects.some((project) => ["traffic", "mixed"].includes(project.impact_type));
  const noiseProject = projects.some((project) => ["noise", "mixed"].includes(project.impact_type));
  const dustProject = projects.some((project) => /permit|construction|demo|dust/i.test(project.title + " " + project.notes));

  return {
    noise: noiseProject ? overall : "LOW",
    traffic: trafficProject ? overall : "LOW",
    dust: dustProject ? overall : "LOW",
  };
}

function topRisks(projects: ScoreProject[]): string[] {
  return projects.map((project) => `${project.title} — ${project.notes}`).slice(0, 3);
}

export default function HomePage() {
  const [address, setAddress] = useState(DEFAULT_ADDRESS);
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const severity = useMemo(
    () => (result ? deriveSeverity(result.score, result.projects) : null),
    [result],
  );
  const risks = useMemo(() => (result ? topRisks(result.projects) : []), [result]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const score = await fetchScore(address);
      setResult(score);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Unable to fetch a disruption score right now.",
      );
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="page">
      <section className="panel">
        <p className="eyebrow">Chicago MVP demo</p>
        <h1>Disruption score lookup</h1>
        <p className="lede">
          Enter a Chicago address to fetch the mocked disruption score from the backend.
        </p>

        <form className="lookup-form" onSubmit={handleSubmit}>
          <label htmlFor="address">Address</label>
          <div className="row">
            <input
              id="address"
              name="address"
              type="text"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="1600 W Chicago Ave, Chicago, IL"
              required
            />
            <button type="submit" disabled={isLoading}>
              {isLoading ? "Loading…" : "Get score"}
            </button>
          </div>
        </form>

        {error ? <p className="error">{error}</p> : null}

        {result ? (
          <section className="results">
            <div className="score-card">
              <p className="score-label">Disruption score</p>
              <div className="score-value">{result.score}</div>
              <p className="score-meta">Confidence: {result.confidence}</p>
              <p className="score-meta">As of: {new Date(result.as_of).toLocaleString()}</p>
            </div>

            <div className="detail-grid">
              <div className="detail-card">
                <h2>Severity</h2>
                <ul>
                  <li>Noise: {severity?.noise ?? "LOW"}</li>
                  <li>Traffic: {severity?.traffic ?? "LOW"}</li>
                  <li>Dust: {severity?.dust ?? "LOW"}</li>
                </ul>
              </div>

              <div className="detail-card">
                <h2>Top risks</h2>
                <ul>
                  {risks.map((risk) => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="detail-card">
              <h2>Explanation</h2>
              <p>{result.explanation}</p>
            </div>
          </section>
        ) : (
          <section className="results empty-state">
            <p>Submit an address to view the disruption score, severity snapshot, and top risks.</p>
          </section>
        )}
      </section>
    </main>
  );
}
