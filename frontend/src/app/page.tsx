"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  ExplanationPanel,
  getConfidenceReasons,
  getMeaningInsights,
  ImpactWindow,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { MapView } from "@/components/map-view";
import { Card, Container, Header, Section } from "@/components/shell";
import { fetchScore, fetchSuggestions, geocodeForMap, ScoreResponse, ScoreSource } from "@/lib/api";

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";
const PREMIUM_PLACEHOLDER = "Search a Chicago address";
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
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [mapCoords, setMapCoords] = useState<{ lat: number; lon: number } | null>(null);
  const searchShellRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const skipSuggestRef = useRef(false);
  const workspaceMode = isLoading || result !== null;
  const confidenceReasons = result ? getConfidenceReasons(result) : [];
  const meaningInsights = result ? getMeaningInsights(result) : [];
  const loadingSteps = [
    "Checking live availability",
    "Evaluating nearby permits and closures",
    "Building the disruption brief",
  ];
  const resultMode = result?.mode ?? scoreSource;
  const isDemoResult = resultMode === "demo";
  const statusHeadline = isDemoResult ? "Demo fallback" : "Live score";
  const statusMessage = isDemoResult
    ? (statusNote ?? "Showing the approved Chicago fallback while live scoring is unavailable.")
    : "Live backend scoring is active for this address lookup.";
  const hasSuggestions = showSuggestions && suggestions.length > 0;
  const activeSuggestionId = activeSuggestionIndex >= 0 ? `address-suggestion-${activeSuggestionIndex}` : undefined;

  const supportingDetails = useMemo(() => {
    if (!result) return [];
    return [
      { label: "Mode", value: isDemoResult ? "Demo fallback" : "Live Chicago scoring" },
      { label: "Confidence", value: result.confidence },
      { label: "Drivers surfaced", value: String(result.top_risks.length) },
      { label: "Sources", value: "Chicago permits • Street closures" },
    ];
  }, [isDemoResult, result]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchShellRef.current && !searchShellRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
        setActiveSuggestionIndex(-1);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Fetch autocomplete suggestions as the user types (debounced 300 ms).
  // skipSuggestRef suppresses the effect when address is set programmatically
  // (e.g. suggestion selection) to prevent the dropdown from reopening.
  useEffect(() => {
    if (skipSuggestRef.current) {
      skipSuggestRef.current = false;
      return;
    }
    if (address.trim().length < 3) {
      setSuggestions([]);
      setShowSuggestions(false);
      setActiveSuggestionIndex(-1);
      return;
    }
    const timer = setTimeout(async () => {
      const results = await fetchSuggestions(address);
      setSuggestions(results);
      setShowSuggestions(results.length > 0);
      setActiveSuggestionIndex(-1);
    }, 300);
    return () => clearTimeout(timer);
  }, [address]);

  useEffect(() => {
    if (!result) {
      setMapCoords(null);
      return;
    }
    if (result.latitude != null && result.longitude != null) {
      setMapCoords({ lat: result.latitude, lon: result.longitude });
      return;
    }
    geocodeForMap(result.address).then((coords) => {
      if (coords) setMapCoords(coords);
    });
  }, [result]);

  function handleSuggestionSelect(suggestion: string) {
    skipSuggestRef.current = true;
    setAddress(suggestion);
    setSuggestions([]);
    setShowSuggestions(false);
    setActiveSuggestionIndex(-1);
    inputRef.current?.focus();
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!hasSuggestions) {
      if (event.key === "ArrowDown" && suggestions.length > 0) {
        setShowSuggestions(true);
        setActiveSuggestionIndex(0);
        event.preventDefault();
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
    } else if (event.key === "Enter" && activeSuggestionIndex >= 0) {
      event.preventDefault();
      handleSuggestionSelect(suggestions[activeSuggestionIndex]);
    } else if (event.key === "Escape") {
      setShowSuggestions(false);
      setActiveSuggestionIndex(-1);
    }
  }

  async function submitAddress(addr: string) {
    setIsLoading(true);
    setError(null);
    try {
      const scoreResult = await fetchScore(addr);
      setResult(scoreResult.score);
      setScoreSource(scoreResult.source);
      if ("note" in scoreResult && scoreResult.note) {
        setStatusNote(scoreResult.note);
      } else {
        setStatusNote(null);
      }
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "The score request could not be completed. Try again in a moment.",
      );
      setResult(null);
      setStatusNote(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAddress(address);
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
            <a href="#examples-section">Examples</a>
          </nav>
        </Header>

        <Section className={`hero-section ${workspaceMode ? "hero-section--workspace" : ""}`}>
          <Card tone="highlighted" className="hero-card">
            <div className={`hero-copy ${workspaceMode ? "hero-copy--workspace" : ""}`}>
              <p className="eyebrow">Chicago address intelligence</p>
              <h1>
                {workspaceMode
                  ? "A decision-ready disruption brief for the current address."
                  : "Assess near-term construction friction before it affects the address."}
              </h1>
              <p className="lede">
                {workspaceMode
                  ? "Keep the current score, reasoning, and spatial context visible while you run another Chicago lookup."
                  : "Surface a clear disruption score, confidence read, strongest drivers, and spatial context in one premium workflow."}
              </p>
            </div>

            <form className={`lookup-form ${workspaceMode ? "lookup-form--workspace" : ""}`} onSubmit={handleSubmit}>
              <label htmlFor="address" className="input-label">
                {workspaceMode ? "Search another Chicago address" : "Chicago address"}
              </label>
              <div ref={searchShellRef} className={`search-shell ${workspaceMode ? "search-shell--workspace" : ""}`}>
                <div className="search-input-stack">
                  <input
                    ref={inputRef}
                    id="address"
                    name="address"
                    type="text"
                    value={address}
                    onChange={(event) => setAddress(event.target.value)}
                    onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                    onKeyDown={handleInputKeyDown}
                    placeholder={PREMIUM_PLACEHOLDER}
                    autoComplete="off"
                    role="combobox"
                    aria-expanded={hasSuggestions}
                    aria-controls="address-suggestions"
                    aria-activedescendant={activeSuggestionId}
                    aria-autocomplete="list"
                    required
                  />
                  {hasSuggestions ? (
                    <ul id="address-suggestions" className="suggestion-list" role="listbox" aria-label="Address suggestions">
                      {suggestions.map((suggestion, index) => (
                        <li
                          key={suggestion}
                          id={`address-suggestion-${index}`}
                          role="option"
                          aria-selected={index === activeSuggestionIndex}
                          className={`suggestion-item ${index === activeSuggestionIndex ? "suggestion-item--active" : ""}`}
                          onMouseDown={() => handleSuggestionSelect(suggestion)}
                          onMouseEnter={() => setActiveSuggestionIndex(index)}
                        >
                          <span className="suggestion-item-label">{suggestion}</span>
                          <span className="suggestion-item-meta">Chicago address</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
                <button type="submit" disabled={isLoading}>
                  {isLoading ? "Analyzing…" : "Analyze address"}
                </button>
              </div>
              <div className={`hero-support ${workspaceMode ? "hero-support--workspace" : ""}`}>
                <p className="form-hint">
                  Returns a score, severity read, strongest drivers, interpretation, and map context for one Chicago address.
                </p>

                <div className="example-row">
                  <span className="example-label">Quick examples</span>
                  <div className="example-chip-group">
                    {EXAMPLE_ADDRESSES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        className="example-chip"
                        onClick={() => handleSuggestionSelect(example)}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </form>

            {(result || statusNote) ? (
              <div className={`status-banner ${isDemoResult ? "status-banner--demo" : "status-banner--live"}`} role="status">
                <span className="status-badge">{statusHeadline}</span>
                <div className="status-copy">
                  <strong>{statusMessage}</strong>
                  <span>{isDemoResult ? "Fallback remains explicit so reviewers know what they are seeing." : "Sources: Chicago permits • Street closures"}</span>
                </div>
              </div>
            ) : null}

            {error ? (
              <div className="feedback-banner" role="alert">
                <p className="feedback-title">Unable to complete the lookup</p>
                <p>{error}</p>
              </div>
            ) : null}
          </Card>
        </Section>

        <Section
          className={workspaceMode ? "workspace-section workspace-section--score" : undefined}
          eyebrow="Score"
          title={workspaceMode ? "Decision brief" : "What the score returns"}
          description={
            workspaceMode
              ? "Read the headline score first, then move directly into interpretation, strongest drivers, and supporting context."
              : "A single lookup returns the headline score, why it matters, and the supporting context behind it."
          }
        >
          <div id="score-section" className="anchor-target" />
          {isLoading ? (
            <section className="results results--loading">
              <Card className="score-card skeleton-card loading-card">
                <p className="loading-kicker">Building disruption brief</p>
                <div className="loading-step-list" aria-live="polite">
                  {loadingSteps.map((step, index) => (
                    <div key={step} className="loading-step">
                      <span className="loading-step-index">0{index + 1}</span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
                <p className="loading-support">Checking live availability first, then assembling a concise address-level brief.</p>
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
            <section className="results results--loaded workspace-flow">
              <div className="workspace-top-grid">
                <Card className="score-card">
                  <ScoreHero result={result} />
                </Card>
                <Card className="detail-card detail-card--summary">
                  <h2>Why this score</h2>
                  <ExplanationPanel explanation={result.explanation} meaning={meaningInsights} />
                </Card>
              </div>

              <div className="detail-grid detail-grid--balanced">
                <Card className="detail-card">
                  <h2>Confidence and severity</h2>
                  <SeverityMeters severity={result.severity} confidence={result.confidence} confidenceReasons={confidenceReasons} />
                </Card>
                <Card className="detail-card supporting-card">
                  <p className="supporting-kicker">Quick read</p>
                  <ul className="supporting-list supporting-list--compact">
                    {supportingDetails.map((item) => (
                      <li key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>

              <div id="signals-section" className="anchor-target" />
              <Section
                eyebrow="Signals"
                title="Strongest supporting drivers"
                description="These are the clearest nearby signals behind the score, followed by the map and timeline context that help interpret them."
                className="workspace-subsection"
              >
                <Card className="detail-card drivers-card">
                  <TopRiskGrid result={result} />
                </Card>
              </Section>

              <div className="support-grid">
                <Card className="detail-card map-card">
                  <div className="map-card-head">
                    <div>
                      <p className="map-kicker">Spatial context</p>
                      <h2>Address and nearby area</h2>
                    </div>
                    <span className="map-badge">OpenStreetMap</span>
                  </div>
                  {mapCoords ? (
                    <MapView latitude={mapCoords.lat} longitude={mapCoords.lon} address={result.address} />
                  ) : (
                    <div className="map-placeholder" aria-label="Locating address on map…">
                      <div className="map-grid" />
                      <div className="map-pin map-pin--primary" />
                    </div>
                  )}
                  <p className="map-copy">Use the map to anchor the score geographically and confirm whether the risk is tied to a major corridor or local site context.</p>
                </Card>

                <div className="support-stack">
                  <Card className="detail-card">
                    <ImpactWindow result={result} />
                  </Card>
                  <Card className="detail-card supporting-card">
                    <p className="supporting-kicker">Review notes</p>
                    <ul className="supporting-list">
                      <li>
                        <span>Interpretation</span>
                        <strong>Read the score as a near-term livability signal, not an exact operational forecast.</strong>
                      </li>
                      <li>
                        <span>Best use</span>
                        <strong>Helpful for screening addresses before site visits, planning, or stakeholder review.</strong>
                      </li>
                      <li>
                        <span>Mode handling</span>
                        <strong>{isDemoResult ? "Fallback state remains visible and intentional for review." : "Live mode is clearly labeled so decision-makers know the score is database-backed."}</strong>
                      </li>
                    </ul>
                  </Card>
                </div>
              </div>
            </section>
          ) : (
            <section className="results">
              <Card className="empty-state">
                <p className="empty-kicker">Ready for analysis</p>
                <h3>Start with a Chicago address to generate a disruption brief.</h3>
                <p>
                  When live scoring is available, the page returns a live address assessment. If not, it falls back gracefully to the approved demo scenario without hiding the mode.
                </p>
              </Card>
            </section>
          )}
        </Section>

        <Section
          id="examples-section"
          eyebrow="Examples"
          title="Fallback and review examples"
          description="Examples stay available for walkthroughs and fallback validation, but they stay below the primary scoring workflow."
          className="demo-section"
        >
          <div className="demo-grid demo-grid--compressed">
            <Card className="detail-card demo-card">
              <p className="supporting-kicker">Chicago examples</p>
              <h2>Load a known address quickly</h2>
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
              <p className="supporting-kicker">Mode behavior</p>
              <ul className="supporting-list">
                <li>
                  <span>Live state</span>
                  <strong>Clearly labeled and presented as the default decision-ready experience.</strong>
                </li>
                <li>
                  <span>Demo fallback</span>
                  <strong>Still visible and explicit, so reviewers can distinguish sample output from live scoring.</strong>
                </li>
              </ul>
            </Card>
          </div>
        </Section>
      </Container>
    </main>
  );
}
