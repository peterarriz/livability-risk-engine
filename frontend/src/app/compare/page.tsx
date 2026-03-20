"use client";

import React, { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ScoreHero, TopRiskGrid, SeverityMeters, getConfidenceReasons } from "@/components/score-experience";
import { Card, Container, Header } from "@/components/shell";
import { fetchScore, fetchSuggestions, ScoreResponse } from "@/lib/api";

function getSeverityColor(score: number): string {
  if (score >= 75) return "severe";
  if (score >= 50) return "high";
  if (score >= 25) return "moderate";
  return "low";
}

type SlotState = {
  address: string;
  result: ScoreResponse | null;
  isLoading: boolean;
  error: string | null;
  suggestions: string[];
  showSuggestions: boolean;
  activeSuggestionIndex: number;
};

function AddressSlot({
  slot,
  label,
  onAddressChange,
  onSubmit,
  onSuggestionSelect,
  onKeyDown,
  onFocus,
  onBlur,
  onSuggestionHover,
  inputRef,
}: {
  slot: SlotState;
  label: string;
  onAddressChange: (value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onSuggestionSelect: (suggestion: string) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onFocus: () => void;
  onBlur: () => void;
  onSuggestionHover: (index: number) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const hasSuggestions = slot.showSuggestions && slot.suggestions.length > 0;
  const activeSuggestionId = slot.activeSuggestionIndex >= 0 ? `suggestion-${label}-${slot.activeSuggestionIndex}` : undefined;

  return (
    <div className="compare-slot">
      <form onSubmit={onSubmit} className="compare-form">
        <label className="input-label">{label}</label>
        <div className="search-shell">
          <div className="search-input-stack">
            <input
              ref={inputRef}
              type="text"
              value={slot.address}
              onChange={(e) => onAddressChange(e.target.value)}
              onFocus={onFocus}
              onBlur={onBlur}
              onKeyDown={onKeyDown}
              placeholder="Enter a Chicago address"
              autoComplete="off"
              role="combobox"
              aria-expanded={hasSuggestions}
              aria-controls={`suggestions-${label}`}
              aria-activedescendant={activeSuggestionId}
              aria-autocomplete="list"
              required
            />
            {hasSuggestions && (
              <ul id={`suggestions-${label}`} className="suggestion-list" role="listbox" aria-label="Address suggestions">
                {slot.suggestions.map((suggestion, index) => (
                  <li
                    key={suggestion}
                    id={`suggestion-${label}-${index}`}
                    role="option"
                    aria-selected={index === slot.activeSuggestionIndex}
                    className={`suggestion-item ${index === slot.activeSuggestionIndex ? "suggestion-item--active" : ""}`}
                    onMouseDown={() => onSuggestionSelect(suggestion)}
                    onMouseEnter={() => onSuggestionHover(index)}
                  >
                    <span className="suggestion-item-label">{suggestion}</span>
                    <span className="suggestion-item-meta">Chicago address</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button type="submit" disabled={slot.isLoading}>
            {slot.isLoading ? "Analyzing…" : "Score"}
          </button>
        </div>
      </form>

      {slot.error && (
        <div className="feedback-banner" role="alert">
          <p className="feedback-title">Lookup unavailable</p>
          <p>{slot.error}</p>
        </div>
      )}

      {slot.isLoading && (
        <Card className="score-card skeleton-card loading-card">
          <p className="loading-kicker">Building disruption brief</p>
          <div className="skeleton skeleton-score" />
          <div className="skeleton skeleton-meta" />
        </Card>
      )}

      {slot.result && !slot.isLoading && (
        <div className="compare-result">
          <Card className={`score-card compare-score-card compare-score-card--${getSeverityColor(slot.result.disruption_score)}`}>
            <ScoreHero result={slot.result} />
          </Card>
          <Card className="detail-card">
            <h2>Severity</h2>
            <SeverityMeters
              severity={slot.result.severity}
              confidence={slot.result.confidence}
              confidenceReasons={getConfidenceReasons(slot.result)}
            />
          </Card>
          <Card className="detail-card drivers-card">
            <TopRiskGrid result={slot.result} />
          </Card>
        </div>
      )}

      {!slot.result && !slot.isLoading && !slot.error && (
        <Card className="empty-state">
          <p className="empty-kicker">Ready for analysis</p>
          <h3>Enter a Chicago address above to score this slot.</h3>
        </Card>
      )}
    </div>
  );
}

function makeSlot(address = ""): SlotState {
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

function ComparePageInner() {
  const searchParams = useSearchParams();
  const initialAddress = searchParams.get("a") ?? "";

  const [slotA, setSlotA] = useState<SlotState>(() => makeSlot(initialAddress));
  const [slotB, setSlotB] = useState<SlotState>(() => makeSlot(""));

  const skipSuggestA = useRef(false);
  const skipSuggestB = useRef(false);
  const inputRefA = useRef<HTMLInputElement>(null);
  const inputRefB = useRef<HTMLInputElement>(null);

  // Auto-score the first slot if an address is pre-filled via query param
  useEffect(() => {
    if (initialAddress.trim().length > 5) {
      scoreSlot("a", initialAddress);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Autocomplete for slot A
  useEffect(() => {
    if (skipSuggestA.current) { skipSuggestA.current = false; return; }
    if (slotA.address.trim().length < 3) {
      setSlotA((s) => ({ ...s, suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 }));
      return;
    }
    const timer = setTimeout(async () => {
      const results = await fetchSuggestions(slotA.address);
      setSlotA((s) => ({ ...s, suggestions: results, showSuggestions: results.length > 0, activeSuggestionIndex: -1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [slotA.address]);

  // Autocomplete for slot B
  useEffect(() => {
    if (skipSuggestB.current) { skipSuggestB.current = false; return; }
    if (slotB.address.trim().length < 3) {
      setSlotB((s) => ({ ...s, suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 }));
      return;
    }
    const timer = setTimeout(async () => {
      const results = await fetchSuggestions(slotB.address);
      setSlotB((s) => ({ ...s, suggestions: results, showSuggestions: results.length > 0, activeSuggestionIndex: -1 }));
    }, 300);
    return () => clearTimeout(timer);
  }, [slotB.address]);

  async function scoreSlot(slot: "a" | "b", address: string) {
    const setSlot = slot === "a" ? setSlotA : setSlotB;
    setSlot((s) => ({ ...s, isLoading: true, error: null, result: null }));
    try {
      const scoreResult = await fetchScore(address);
      setSlot((s) => ({ ...s, isLoading: false, result: scoreResult.score }));
    } catch (err) {
      setSlot((s) => ({
        ...s,
        isLoading: false,
        error: err instanceof Error ? err.message : "Live data temporarily unavailable.",
      }));
    }
  }

  function handleSuggestionSelect(slot: "a" | "b", suggestion: string) {
    if (slot === "a") {
      skipSuggestA.current = true;
      setSlotA((s) => ({ ...s, address: suggestion, suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 }));
      inputRefA.current?.focus();
    } else {
      skipSuggestB.current = true;
      setSlotB((s) => ({ ...s, address: suggestion, suggestions: [], showSuggestions: false, activeSuggestionIndex: -1 }));
      inputRefB.current?.focus();
    }
  }

  function handleKeyDown(slot: "a" | "b", e: React.KeyboardEvent<HTMLInputElement>) {
    const current = slot === "a" ? slotA : slotB;
    const setSlot = slot === "a" ? setSlotA : setSlotB;
    const hasSuggestions = current.showSuggestions && current.suggestions.length > 0;

    if (!hasSuggestions) {
      if (e.key === "ArrowDown" && current.suggestions.length > 0) {
        setSlot((s) => ({ ...s, showSuggestions: true, activeSuggestionIndex: 0 }));
        e.preventDefault();
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSlot((s) => ({ ...s, activeSuggestionIndex: (s.activeSuggestionIndex + 1) % s.suggestions.length }));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSlot((s) => ({
        ...s,
        activeSuggestionIndex: s.activeSuggestionIndex <= 0 ? s.suggestions.length - 1 : s.activeSuggestionIndex - 1,
      }));
    } else if (e.key === "Enter" && current.activeSuggestionIndex >= 0) {
      e.preventDefault();
      handleSuggestionSelect(slot, current.suggestions[current.activeSuggestionIndex]);
    } else if (e.key === "Escape") {
      setSlot((s) => ({ ...s, showSuggestions: false, activeSuggestionIndex: -1 }));
    }
  }

  const bothScored = slotA.result !== null && slotB.result !== null;
  const scoreDiff = bothScored ? slotA.result!.disruption_score - slotB.result!.disruption_score : null;

  return (
    <main className="page page--workspace">
      <Container>
        <Header className="topbar topbar--workspace">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">LR</div>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">Chicago disruption intelligence</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <a href="/">← Back to search</a>
          </nav>
        </Header>

        <section className="workspace-section">
          <div className="section-head">
            <p className="eyebrow">Compare</p>
            <h1>Side-by-side address comparison</h1>
            <p className="lede">Score two Chicago addresses at once to compare disruption risk, severity signals, and key drivers.</p>
          </div>

          {bothScored && scoreDiff !== null && (
            <div className={`status-banner ${Math.abs(scoreDiff) < 10 ? "status-banner--live" : "status-banner--demo"}`} role="status">
              <span className="status-badge">Comparison</span>
              <div className="status-copy">
                {Math.abs(scoreDiff) < 5 ? (
                  <strong>These addresses have similar disruption risk levels.</strong>
                ) : scoreDiff > 0 ? (
                  <strong>Address A scores {Math.abs(scoreDiff)} points higher — it carries more near-term disruption risk.</strong>
                ) : (
                  <strong>Address B scores {Math.abs(scoreDiff)} points higher — it carries more near-term disruption risk.</strong>
                )}
              </div>
            </div>
          )}

          <div className="compare-grid">
            <AddressSlot
              slot={slotA}
              label="Address A"
              onAddressChange={(value) => setSlotA((s) => ({ ...s, address: value }))}
              onSubmit={(e) => { e.preventDefault(); scoreSlot("a", slotA.address); }}
              onSuggestionSelect={(suggestion) => handleSuggestionSelect("a", suggestion)}
              onKeyDown={(e) => handleKeyDown("a", e)}
              onFocus={() => slotA.suggestions.length > 0 && setSlotA((s) => ({ ...s, showSuggestions: true }))}
              onBlur={() => setTimeout(() => setSlotA((s) => ({ ...s, showSuggestions: false })), 150)}
              onSuggestionHover={(index) => setSlotA((s) => ({ ...s, activeSuggestionIndex: index }))}
              inputRef={inputRefA}
            />
            <AddressSlot
              slot={slotB}
              label="Address B"
              onAddressChange={(value) => setSlotB((s) => ({ ...s, address: value }))}
              onSubmit={(e) => { e.preventDefault(); scoreSlot("b", slotB.address); }}
              onSuggestionSelect={(suggestion) => handleSuggestionSelect("b", suggestion)}
              onKeyDown={(e) => handleKeyDown("b", e)}
              onFocus={() => slotB.suggestions.length > 0 && setSlotB((s) => ({ ...s, showSuggestions: true }))}
              onBlur={() => setTimeout(() => setSlotB((s) => ({ ...s, showSuggestions: false })), 150)}
              onSuggestionHover={(index) => setSlotB((s) => ({ ...s, activeSuggestionIndex: index }))}
              inputRef={inputRefB}
            />
          </div>
        </section>
      </Container>
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={
      <main className="page page--workspace">
        <Container>
          <div className="empty-state">
            <p className="empty-kicker">Loading…</p>
          </div>
        </Container>
      </main>
    }>
      <ComparePageInner />
    </Suspense>
  );
}
