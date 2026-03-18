"use client";

import { FormEvent, useState } from "react";

import {
  ExplanationPanel,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { Card, Container, Header, Section } from "@/components/shell";
import { fetchScore, ScoreResponse, ScoreSource } from "@/lib/api";

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
  const [scoreSource, setScoreSource] = useState<ScoreSource>("live");
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workspaceMode = isLoading || result !== null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const scoreResult = await fetchScore(address);
      setResult(scoreResult.score);
      setScoreSource(scoreResult.source);
      setStatusNote(scoreResult.note ?? null);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Unable to fetch a disruption score right now.",
      );
      setResult(null);
      setStatusNote(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className={`page ${workspaceMode ? "page--workspace" : "page--explore"}`}>
      <Container>
        <Header className={`topbar ${workspaceMode ? "topbar--workspace" : ""}`}>
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
            {workspaceMode ? <span className="topnav-label">Viewing</span> : null}
            {workspaceMode ? <span className="topnav-address">{result?.address ?? address}</span> : null}
            <a href="#score-section">Score</a>
            <a href="#signals-section">Signals</a>
            <a href="#demo-section">Demo</a>
          </nav>
        </Header>

        <Section className={`hero-section ${workspaceMode ? "hero-section--workspace" : ""}`}>
          <Card tone="highlighted" className="hero-card">
            <div className={`hero-copy ${workspaceMode ? "hero-copy--workspace" : ""}`}>
              <p className="eyebrow">Chicago MVP demo</p>
              <h1>
                {workspaceMode
                  ? "Workspace mode for active disruption analysis."
                  : "Know the disruption profile of an address before you commit."}
              </h1>
              <p className="lede">
                {workspaceMode
                  ? "Search again instantly while keeping the current score, severity, drivers, and explanation visible in a structured product workspace."
                  : "A premium product shell for surfacing near-term construction friction with a crisp score, interpretable severity, and decision-ready narrative."}
              </p>
            </div>

            <form
              className={`lookup-form ${workspaceMode ? "lookup-form--workspace" : ""}`}
              onSubmit={handleSubmit}
            >
              <label htmlFor="address" className="input-label">
                {workspaceMode ? "Search another Chicago address" : "Chicago address"}
              </label>
              <div className={`search-shell ${workspaceMode ? "search-shell--workspace" : ""}`}>
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
              <div className={`hero-support ${workspaceMode ? "hero-support--workspace" : ""}`}>
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
              </div>
            </form>

            {statusNote ? (
              <div className="status-banner status-banner--demo" role="status">
                <span className="status-badge">{scoreSource === "demo" ? "Demo data" : "Live data"}</span>
                <span>{statusNote}</span>
              </div>
            ) : null}

            {error ? (
              <div className="feedback-banner" role="alert">
                {error}
              </div>
            ) : null}
          </Card>
        </Section>

        <Section
          className={workspaceMode ? "workspace-section workspace-section--score" : undefined}
          eyebrow="Score"
          title={workspaceMode ? "Score workspace" : "Decision-ready output"}
          description={
            workspaceMode
              ? "The score section anchors the analysis workspace with the strongest signal, severity, and explanation."
              : "The layout below is designed to support a high-stakes demo even before richer data visualizations are added."
          }
        >
          <div id="score-section" className="anchor-target" />
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
            <section className="results results--loaded workspace-grid">
              <div className="workspace-main">
                <Card className="score-card">
                  <ScoreHero result={result} />
                </Card>

                <div className="detail-grid detail-grid--workspace">
                  <Card className="detail-card">
                    <h2>Confidence Level & Severity</h2>
                    <SeverityMeters severity={result.severity} />
                  </Card>

                  <Card className="detail-card narrative-card">
                    <h2>Explanation</h2>
                    <ExplanationPanel explanation={result.explanation} />
                  </Card>
                </div>
              </div>

              <aside className="workspace-sidebar">
                <div id="signals-section" className="anchor-target" />
                <Section
                  eyebrow="Signals"
                  title="Evidence and supporting context"
                  description="These sections expose the strongest drivers, spatial grounding, and supporting details that sit behind the score."
                  className="sidebar-section"
                >
                  <Card className="detail-card map-card">
                    <div className="map-card-head">
                      <div>
                        <p className="map-kicker">Spatial context</p>
                        <h2>Map view</h2>
                      </div>
                      <span className="map-badge">Coming soon</span>
                    </div>
                    <div className="map-placeholder" aria-hidden="true">
                      <div className="map-grid" />
                      <div className="map-pin map-pin--primary" />
                      <div className="map-pin map-pin--secondary" />
                      <div className="map-pin map-pin--tertiary" />
                    </div>
                    <p className="map-copy">
                      Location-aware context will land here next. For now, this placeholder grounds
                      the score in a real-world workspace layout.
                    </p>
                  </Card>

                  <Card className="detail-card">
                    <h2>Primary Drivers</h2>
                    <TopRiskGrid result={result} />
                  </Card>

                  <Card className="detail-card supporting-card">
                    <p className="supporting-kicker">Supporting details</p>
                    <ul className="supporting-list">
                      <li>
                        <span>Address</span>
                        <strong>{result.address}</strong>
                      </li>
                      <li>
                        <span>Confidence Level</span>
                        <strong>{result.confidence}</strong>
                      </li>
                      <li>
                        <span>Top risks surfaced</span>
                        <strong>{result.top_risks.length}</strong>
                      </li>
                    </ul>
                  </Card>
                </Section>
              </aside>
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

        <Section
          id="demo-section"
          eyebrow="Demo"
          title="How this demo works"
          description="A single-page investor-ready flow that shows the score, supporting signals, and product framing without requiring hidden routes or extra setup."
          className="demo-section"
        >
          <div className="demo-grid">
            <Card className="detail-card demo-card">
              <p className="supporting-kicker">Examples</p>
              <h2>Present three strong Chicago scenarios</h2>
              <div className="example-chip-group example-chip-group--demo">
                {EXAMPLE_ADDRESSES.map((example) => (
                  <button
                    key={`demo-${example}`}
                    type="button"
                    className="example-chip"
                    onClick={() => {
                      setAddress(example);
                      window.location.hash = "#score-section";
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </Card>

            <Card className="detail-card demo-card">
              <p className="supporting-kicker">How it works</p>
              <ul className="supporting-list">
                <li>
                  <span>Score</span>
                  <strong>Summarizes near-term disruption into one clear product moment.</strong>
                </li>
                <li>
                  <span>Signals</span>
                  <strong>Explains the evidence and why the score should be trusted.</strong>
                </li>
                <li>
                  <span>Demo mode</span>
                  <strong>Falls back to sample data gracefully when live backend access is unavailable.</strong>
                </li>
              </ul>
            </Card>
          </div>
        </Section>
      </Container>
    </main>
  );
}
