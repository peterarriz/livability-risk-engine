"use client";

import React, { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

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
  const [address, setAddress] = useState("");
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [scoreSource, setScoreSource] = useState<ScoreSource>("live");
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [mapCoords, setMapCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState("");
  const [addressHistory, setAddressHistory] = useState<string[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const searchShellRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const skipSuggestRef = useRef(false);
  // Only fetch suggestions after the user has actually typed — prevents the
  // dropdown firing on mount or when an address is set programmatically.
  const hasUserTyped = useRef(false);
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
  const statusHeadline = isDemoResult ? "Sample data" : "Live score";
  const statusMessage = isDemoResult
    ? (statusNote ?? "The backend returned sample data. Connect a database to enable live scoring.")
    : "Live backend scoring is active for this address lookup.";
  const hasSuggestions = showSuggestions && suggestions.length > 0;
  const activeSuggestionId = activeSuggestionIndex >= 0 ? `address-suggestion-${activeSuggestionIndex}` : undefined;

  type DetailItem = { label: string; value: string; isConfidence?: boolean };
  const supportingDetails = useMemo((): DetailItem[] => {
    if (!result) return [];
    return [
      { label: "Data mode", value: isDemoResult ? "Demo fallback" : "Live Chicago feed" },
      { label: "Confidence", value: result.confidence, isConfidence: true },
      { label: "Active signals detected", value: String(result.top_risks.length) },
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
  // Only runs when hasUserTyped is true — prevents the dropdown from opening
  // on mount or when an address is set programmatically (suggestion selection).
  // skipSuggestRef suppresses a single effect run after programmatic selection.
  useEffect(() => {
    if (!hasUserTyped.current) return;
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
      // Only update if the input is still focused when results arrive.
      if (isFocused) {
        setSuggestions(results);
        setShowSuggestions(results.length > 0);
        setActiveSuggestionIndex(-1);
      }
    }, 300);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
    hasUserTyped.current = false;   // treat the fill as programmatic
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
      // Track address history (last 5, deduplicated)
      setAddressHistory((prev: string[]) => {
        const deduped = [addr, ...prev.filter((a: string) => a !== addr)];
        return deduped.slice(0, 5);
      });
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Live data temporarily unavailable. Try again in a moment.",
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
            {workspaceMode ? (
              <a href="#" className="topnav-address" onClick={(e: React.MouseEvent) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }} title="Scroll to top">
                {result?.address ?? address}
              </a>
            ) : null}
            {workspaceMode && addressHistory.length > 1 ? (
              <div className="history-dropdown-shell">
                <button
                  type="button"
                  className="history-btn"
                  onClick={() => setShowHistory((v: boolean) => !v)}
                  aria-expanded={showHistory}
                  aria-label="Recent addresses"
                >
                  🕐 Recent
                </button>
                {showHistory ? (
                  <ul className="history-dropdown" role="listbox" aria-label="Recent addresses">
                    {addressHistory.slice(1).map((hist: string) => (
                      <li key={hist} role="option" aria-selected={false}>
                        <button type="button" onClick={() => { handleSuggestionSelect(hist); setShowHistory(false); }}>
                          {hist}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            <a href="#score-section">Score</a>
            <a href="#signals-section">Signals</a>
            <a href="#examples-section">Examples</a>
            <a href="#pricing-section" className="topnav-pricing">Pricing</a>
          </nav>
        </Header>

        <Section className={`hero-section ${workspaceMode ? "hero-section--workspace" : ""}`}>
          <Card tone="highlighted" className="hero-card">
            <div className={`hero-copy ${workspaceMode ? "hero-copy--workspace" : ""}`}>
              <p className="eyebrow">Chicago address intelligence</p>
              <h1>
                {workspaceMode
                  ? "A decision-ready disruption brief for the current address."
                  : "Instant disruption intelligence for any Chicago address."}
              </h1>
              <p className="lede">
                {workspaceMode
                  ? "Run another lookup below. Score, reasoning, and spatial context update automatically."
                  : "Enter an address to get a real-time disruption score powered by live Chicago permit and street closure data — in under 10 seconds."}
              </p>
            </div>

            <form className={`lookup-form ${workspaceMode ? "lookup-form--workspace" : ""}`} onSubmit={handleSubmit}>
              <label htmlFor="address" className="input-label">
                Enter a Chicago address
              </label>
              <div ref={searchShellRef} className={`search-shell ${workspaceMode ? "search-shell--workspace" : ""}`}>
                <div className="search-input-stack">
                  <input
                    ref={inputRef}
                    id="address"
                    name="address"
                    type="text"
                    value={address}
                    onChange={(event) => {
                      hasUserTyped.current = true;
                      setAddress(event.target.value);
                    }}
                    onFocus={() => setIsFocused(true)}
                    onBlur={() => {
                      setIsFocused(false);
                      setTimeout(() => setShowSuggestions(false), 150);
                    }}
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
                <p className="form-disclaimer">Currently covers Chicago, IL addresses only.</p>

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
                <p className="feedback-title">
                  {error.toLowerCase().includes("not found") || error.toLowerCase().includes("couldn't find")
                    ? "Address not found"
                    : "Lookup unavailable"}
                </p>
                <p>
                  {error.toLowerCase().includes("not found") || error.toLowerCase().includes("couldn't find")
                    ? "We couldn't find that address in Chicago. Try including a ZIP code."
                    : "Live data temporarily unavailable. Try again in a moment, or use one of the example addresses below."}
                </p>
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
          headerAction={workspaceMode && result ? (
            <button
              type="button"
              className="icon-btn"
              title="PDF export is available on the Pro plan"
              onClick={() => alert("PDF export is available on the Pro plan — see Pricing for details.")}
            >
              ↓ Export PDF
            </button>
          ) : undefined}
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
              {result.disruption_score >= 61 && (
                <div className="pro-badge-bar">
                  <span className="pro-badge-icon">⚠</span>
                  <span>
                    <strong>High-risk address detected.</strong> Pro users get 30-day forecasts and permit detail exports.{" "}
                    <a href="#pricing-section" className="pro-badge-link">See Pro plan →</a>
                  </span>
                </div>
              )}

              <div className="workspace-top-grid">
                <Card className="score-card">
                  <ScoreHero result={result} />
                  <div className="score-actions">
                    <button type="button" className="action-btn" onClick={() => setShowSaveModal(true)}>
                      Save report
                    </button>
                    <a href="#" className="compare-link" onClick={(e) => e.preventDefault()}>
                      Compare with another address →
                    </a>
                  </div>
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
                        {"isConfidence" in item && item.isConfidence ? (
                          <strong className="confidence-value">
                            <span className={`confidence-dot confidence-dot--${item.value.toLowerCase()}`} aria-hidden="true" />
                            {item.value}
                          </strong>
                        ) : (
                          <strong>{item.value}</strong>
                        )}
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
                    <MapView latitude={mapCoords.lat} longitude={mapCoords.lon} address={result.address} signals={result.nearby_signals ?? []} />
                  ) : (
                    <div className="map-placeholder" aria-label="Locating address on map…">
                      <div className="map-grid" />
                      <div className="map-pin map-pin--primary" />
                    </div>
                  )}
                  <p className="map-copy">Colored circles show nearby permit and closure locations. Click any circle for signal details. Circle size and opacity reflect disruption weight — larger and more saturated means higher impact.</p>
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
                        <strong>This score reflects near-term conditions, not long-term neighborhood quality.</strong>
                      </li>
                      <li>
                        <span>Best use</span>
                        <strong>Helpful for screening addresses before site visits, planning, or stakeholder review.</strong>
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
                <h3>Enter a Chicago address above to get an instant disruption score.</h3>
                <p>
                  The score is powered by live city permit and street closure data. Results return in under 10 seconds.
                </p>
              </Card>
            </section>
          )}
        </Section>

        <Section
          id="pricing-section"
          eyebrow="Pricing"
          title="Choose the right plan"
          description="Start free. Upgrade when you need forecasts, exports, and team access."
          className="pricing-section"
        >
          <div className="pricing-grid">
            <Card className="detail-card pricing-card">
              <p className="supporting-kicker">Free</p>
              <h2>$0 / month</h2>
              <ul className="pricing-features">
                <li>Unlimited address lookups</li>
                <li>Real-time disruption score</li>
                <li>Signal cards and confidence read</li>
                <li>Spatial map context</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--secondary">Get started free</button>
            </Card>
            <Card className="detail-card pricing-card pricing-card--pro">
              <p className="supporting-kicker">Pro</p>
              <h2>$49 / month</h2>
              <ul className="pricing-features">
                <li>Everything in Free</li>
                <li>30-day disruption forecasts</li>
                <li>PDF and CSV report exports</li>
                <li>Permit detail drill-down</li>
                <li>Address comparison tool</li>
                <li>Priority data refresh</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--primary">Start Pro trial</button>
            </Card>
          </div>
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

      {showSaveModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Save report" onClick={() => setShowSaveModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-close" aria-label="Close" onClick={() => setShowSaveModal(false)}>×</button>
            <p className="supporting-kicker">Save report</p>
            <h3>Create a free account to save and share this report.</h3>
            <p className="modal-copy">Your disruption brief for {result?.address} will be saved to your account and shareable via link.</p>
            <input
              type="email"
              placeholder="your@email.com"
              value={saveEmail}
              onChange={(e) => setSaveEmail(e.target.value)}
              aria-label="Email address"
            />
            <button type="button" className="modal-cta">Create free account</button>
            <p className="modal-fine-print">No credit card required. Free plan includes unlimited lookups.</p>
          </div>
        </div>
      )}
    </main>
  );
}
