"use client";

import { FormEvent, useState } from "react";

import { ApiError, fetchScore, ScoreResponse } from "@/lib/api";

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";

export default function HomePage() {
  const [address, setAddress] = useState(DEFAULT_ADDRESS);
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const score = await fetchScore(address);
      setResult(score);
    } catch (submissionError) {
      setError(
        submissionError instanceof ApiError
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
          Enter a Chicago address to fetch the demo-ready disruption score response.
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
              <div className="score-value">{result.disruption_score}</div>
              <p className="score-meta">Confidence: {result.confidence}</p>
            </div>

            <div className="detail-grid">
              <div className="detail-card">
                <h2>Severity</h2>
                <ul>
                  <li>Noise: {result.severity.noise}</li>
                  <li>Traffic: {result.severity.traffic}</li>
                  <li>Dust: {result.severity.dust}</li>
                </ul>
              </div>

              <div className="detail-card">
                <h2>Top risks</h2>
                <ul>
                  {result.top_risks.map((risk) => (
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
