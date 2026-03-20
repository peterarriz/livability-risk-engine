"use client";

// data-023: Side-by-side address comparison page
// URL: /compare?a=<address-A>&b=<address-B>
// Pre-fills address A from the query param so the user arrives from the main page
// with one address already loaded.

import React, { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  ExplanationPanel,
  getMeaningInsights,
  ScoreHero,
  SeverityMeters,
  TopRiskGrid,
} from "@/components/score-experience";
import { Card, Container, Section } from "@/components/shell";
import { fetchScore, fetchSuggestions, ScoreResponse } from "@/lib/api";

const PLACEHOLDER = "Search a Chicago address";

type AddressSlotState = {
  address: string;
  result: ScoreResponse | null;
  isLoading: boolean;
  error: string | null;
  suggestions: string[];
  showSuggestions: boolean;
  activeSuggestionIndex: number;
};

function initSlot(address = ""): AddressSlotState {
  return {
    address,
    result: null,
    isLoading: false,
    error: null,
    suggestions: [],
    showSuggestions: false,
    activeSuggestionIndex: -1,
  };
}

type SlotKey = "a" | "b";

export default function ComparePage() {
  const [slots, setSlots] = useState<Record<SlotKey, AddressSlotState>>({
    a: initSlot(),
    b: initSlot(),
  });

  const skipSuggestRef = useRef<Record<SlotKey, boolean>>({ a: false, b: false });
  const shellRef = useRef<HTMLDivElement>(null);

  // Pre-fill slot A from the ?a= query param on mount.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const paramA = params.get("a");
    if (paramA) {
      setSlots((prev) => ({
        ...prev,
        a: { ...prev.a, address: paramA },
      }));
    }
  }, []);

  // Auto-submit slot A once its address is set from query param.
  const didAutoSubmitRef = useRef(false);
  useEffect(() => {
    if (didAutoSubmitRef.current) return;
    const params = new URLSearchParams(window.location.search);
    const paramA = params.get("a");
    if (paramA && slots.a.address === paramA && !slots.a.result && !slots.a.isLoading) {
      didAutoSubmitRef.current = true;
      submitAddress("a", paramA);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots.a.address]);

  // Close suggestion dropdowns on outside click.
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (shellRef.current && !shellRef.current.contains(event.target as Node)) {
        setSlots((prev) => ({
          a: { ...prev.a, showSuggestions: false, activeSuggestionIndex: -1 },
          b: { ...prev.b, showSuggestions: false, activeSuggestionIndex: -1 },
        }));
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function updateSlot(key: SlotKey, patch: Partial<AddressSlotState>) {
    setSlots((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  }

  const debouncerRef = useRef<Record<SlotKey, ReturnType<typeof setTimeout> | null>>({
    a: null,
    b: null,
  });

  function handleAddressChange(key: SlotKey, value: string) {
    if (skipSuggestRef.current[key]) {
      skipSuggestRef.current[key] = false;
      updateSlot(key, { address: value });
      return;
    }
    updateSlot(key, { address: value });

    if (debouncerRef.current[key]) clearTimeout(debouncerRef.current[key]!);
    if (value.trim().length < 3) {
      updateSlot(key, { suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 });
      return;
    }
    debouncerRef.current[key] = setTimeout(async () => {
      const results = await fetchSuggestions(value);
      setSlots((prev) => ({
        ...prev,
        [key]: { ...prev[key], suggestions: results, showSuggestions: results.length > 0, activeSuggestionIndex: -1 },
      }));
    }, 300);
  }

  function handleSuggestionSelect(key: SlotKey, suggestion: string) {
    skipSuggestRef.current[key] = true;
    updateSlot(key, { address: suggestion, suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 });
  }

  function handleKeyDown(key: SlotKey, event: React.KeyboardEvent<HTMLInputElement>) {
    const slot = slots[key];
    if (!slot.showSuggestions || slot.suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      updateSlot(key, { activeSuggestionIndex: (slot.activeSuggestionIndex + 1) % slot.suggestions.length });
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      updateSlot(key, { activeSuggestionIndex: slot.activeSuggestionIndex <= 0 ? slot.suggestions.length - 1 : slot.activeSuggestionIndex - 1 });
    } else if (event.key === "Enter" && slot.activeSuggestionIndex >= 0) {
      event.preventDefault();
      handleSuggestionSelect(key, slot.suggestions[slot.activeSuggestionIndex]);
    } else if (event.key === "Escape") {
      updateSlot(key, { showSuggestions: false, activeSuggestionIndex: -1 });
    }
  }

  const submitAddress = useCallback(async (key: SlotKey, addr: string) => {
    if (!addr.trim()) return;
    updateSlot(key, { isLoading: true, error: null, result: null });
    try {
      const { score } = await fetchScore(addr);
      setSlots((prev) => ({ ...prev, [key]: { ...prev[key], result: score, isLoading: false } }));
    } catch (err) {
      setSlots((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          isLoading: false,
          error: err instanceof Error ? err.message : "Scoring unavailable.",
        },
      }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(key: SlotKey, event: FormEvent) {
    event.preventDefault();
    submitAddress(key, slots[key].address);
  }

  const labels: Record<SlotKey, string> = { a: "Address A", b: "Address B" };
  const resultA = slots.a.result;
  const resultB = slots.b.result;
  const bothReady = resultA && resultB;

  function scoreDiff(): number | null {
    if (!resultA || !resultB) return null;
    return resultA.disruption_score - resultB.disruption_score;
  }

  const diff = scoreDiff();

  return (
    <main>
      <Container>
        <div className="report-header">
          <a href="/" className="report-back-link">← Back to Livability Risk Engine</a>
        </div>

        <Section
          eyebrow="Compare"
          title="Side-by-side address comparison"
          description="Score two Chicago addresses at once to see which has more near-term disruption risk."
        >
          <div ref={shellRef} className="compare-input-grid">
            {(["a", "b"] as SlotKey[]).map((key) => {
              const slot = slots[key];
              return (
                <Card key={key} className="detail-card compare-input-card">
                  <p className="supporting-kicker">{labels[key]}</p>
                  <form onSubmit={(e) => handleSubmit(key, e)} className="compare-form" autoComplete="off">
                    <div className="search-shell" style={{ position: "relative" }}>
                      <input
                        type="text"
                        value={slot.address}
                        onChange={(e) => handleAddressChange(key, e.target.value)}
                        onKeyDown={(e) => handleKeyDown(key, e)}
                        onFocus={() => slot.suggestions.length > 0 && updateSlot(key, { showSuggestions: true })}
                        placeholder={PLACEHOLDER}
                        aria-label={`${labels[key]} input`}
                        aria-autocomplete="list"
                        className="search-input"
                        disabled={slot.isLoading}
                        autoComplete="off"
                      />
                      <button type="submit" className="search-btn" disabled={slot.isLoading || !slot.address.trim()}>
                        {slot.isLoading ? "…" : "Score"}
                      </button>
                      {slot.showSuggestions && slot.suggestions.length > 0 && (
                        <ul className="suggestions-list" role="listbox">
                          {slot.suggestions.map((s, i) => (
                            <li
                              key={s}
                              id={`compare-${key}-suggestion-${i}`}
                              role="option"
                              aria-selected={i === slot.activeSuggestionIndex}
                              className={`suggestion-item${i === slot.activeSuggestionIndex ? " suggestion-item--active" : ""}`}
                              onMouseDown={() => handleSuggestionSelect(key, s)}
                            >
                              {s}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </form>
                  {slot.error && <p className="modal-error">{slot.error}</p>}
                </Card>
              );
            })}
          </div>

          {bothReady && diff !== null && (
            <Card className="detail-card compare-verdict-card">
              <p className="supporting-kicker">Verdict</p>
              {diff === 0 ? (
                <h3>Both addresses score equally — no clear advantage on disruption risk.</h3>
              ) : (
                <h3>
                  <strong>{diff > 0 ? slots.b.result!.address : slots.a.result!.address}</strong>
                  {" "}has lower near-term disruption risk by{" "}
                  <strong>{Math.abs(diff)} points</strong>.
                </h3>
              )}
              <div className="compare-score-row">
                <div className="compare-score-chip">
                  <span className="supporting-kicker">A</span>
                  <span className="compare-score-value">{resultA.disruption_score}</span>
                  <span className="compare-score-label">{resultA.address}</span>
                </div>
                <span className="compare-vs">vs</span>
                <div className="compare-score-chip">
                  <span className="supporting-kicker">B</span>
                  <span className="compare-score-value">{resultB.disruption_score}</span>
                  <span className="compare-score-label">{resultB.address}</span>
                </div>
              </div>
            </Card>
          )}

          {(resultA || resultB) && (
            <div className="compare-results-grid">
              {(["a", "b"] as SlotKey[]).map((key) => {
                const slot = slots[key];
                if (!slot.result) return null;
                const score = slot.result;
                const meaning = getMeaningInsights(score);
                return (
                  <div key={key} className="compare-result-col">
                    <p className="supporting-kicker compare-col-label">{labels[key]}</p>
                    <Card className="score-card">
                      <ScoreHero result={score} />
                    </Card>
                    <Card className="detail-card detail-card--summary">
                      <h2>Why this score</h2>
                      <ExplanationPanel explanation={score.explanation} meaning={meaning} />
                    </Card>
                    <Card className="detail-card">
                      <h2>Confidence and severity</h2>
                      <SeverityMeters severity={score.severity} confidence={score.confidence} confidenceReasons={[]} />
                    </Card>
                    <Card className="detail-card drivers-card">
                      <h2>Strongest signals</h2>
                      <TopRiskGrid result={score} />
                    </Card>
                  </div>
                );
              })}
            </div>
          )}
        </Section>
      </Container>
    </main>
  );
}
