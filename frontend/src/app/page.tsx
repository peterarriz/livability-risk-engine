"use client";

import { FormEvent, useState } from "react";

import {
  ExplanationPanel,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { Card, Container, Header, Section } from "@/components/shell";
import { ApiError, fetchScore, ScoreResponse } from "@/lib/api";

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";
const PREMIUM_PLACEHOLDER = "Try 1600 W Chicago Ave, Chicago, IL";
const EXAMPLE_ADDRESSES = [
  "1600 W Chicago Ave, Chicago, IL",
  "700 W Grand Ave, Chicago, IL",
  "233 S Wacker Dr, Chicago, IL",
];

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
      <Container>
        <Header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">
              LR
            </div>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">Chicago disruption intelligence</p>
            </div>
          </div>

          <nav className="topnav" aria-label="Primary">
            <span>Score</span>
            <span>Signals</span>
            <span>Demo</span>
          </nav>
        </Header>

        <Section className="hero-section">
          <Card tone="highlighted" className="hero-card">
            <div className="hero-copy">
              <p className="eyebrow">Chicago MVP demo</p>
              <h1>Know the disruption profile of an address before you commit.</h1>
              <p className="lede">
                A premium product shell for surfacing near-term construction friction with a
                crisp score, interpretable severity, and decision-ready narrative.
              </p>
            </div>

            <form className="lookup-form" onSubmit={handleSubmit}>
              <label htmlFor="address" className="input-label">
                Chicago address
              </label>
              <div className="search-shell">
                <input
                  id="address"
                  name="address"
                  type="text"
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  placeholder={PREMIUM_PLACEHOLDER}
                  required
                />
                <button type="submit" disabled={isLoading}>
                  {isLoading ? "Analyzing…" : "Analyze address"}
                </button>
              </div>
              <p className="form-hint">
                Demo output includes disruption score, confidence, severity, top risks, and
                explanation.
              </p>

              <div className="example-row">
                <span className="example-label">Try an example</span>
                <div className="example-chip-group">
                  {EXAMPLE_ADDRESSES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      className="example-chip"
                      onClick={() => setAddress(example)}
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            </form>

            {error ? (
              <div className="feedback-banner" role="alert">
                {error}
              </div>
            ) : null}
          </Card>
        </Section>

        <Section
          eyebrow="Results"
          title="Decision-ready output"
          description="The layout below is designed to support a high-stakes demo even before richer data visualizations are added."
        >
          {isLoading ? (
            <section className="results results--loading">
              <Card className="score-card skeleton-card">
                <div className="skeleton skeleton-label" />
                <div className="skeleton skeleton-score" />
                <div className="skeleton skeleton-meta" />
              </Card>

              <div className="detail-grid">
                <Card className="detail-card skeleton-card">
                  <div className="skeleton skeleton-title" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line short" />
                </Card>

                <Card className="detail-card skeleton-card">
                  <div className="skeleton skeleton-title" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line short" />
                </Card>
              </div>
            </section>
          ) : result ? (
            <section className="results results--loaded">
              <Card className="score-card">
                <ScoreHero result={result} />
              </Card>

              <div className="detail-grid">
                <Card className="detail-card">
                  <h2>Confidence Level & Severity</h2>
                  <SeverityMeters severity={result.severity} />
                </Card>

                <Card className="detail-card">
                  <h2>Primary Drivers</h2>
                  <TopRiskGrid result={result} />
                </Card>
              </div>

              <Card className="detail-card narrative-card">
                <h2>Explanation</h2>
                <ExplanationPanel explanation={result.explanation} />
              </Card>
            </section>
          ) : (
            <section className="results">
              <Card className="empty-state">
                <p className="empty-kicker">Ready for analysis</p>
                <h3>Start with a Chicago address to generate a polished disruption brief.</h3>
                <p>
                  The empty state is intentionally designed to feel complete and presentation-ready,
                  with space reserved for score, severity, top risks, and narrative context.
                </p>
              </Card>
            </section>
          )}
        </Section>
      </Container>
    </main>
  );
}
