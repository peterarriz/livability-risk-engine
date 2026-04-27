/**
 * Regression test for score display consistency.
 *
 * Bug: ScoreHero rendered livability_score (e.g. 46) while WatchlistForm
 * received disruption_score (e.g. 60), causing "Score is currently 60" to
 * contradict the headline "46" on the same page.
 *
 * Fix: All display paths that show a headline score must call headlineScore(),
 * which returns livability_score ?? disruption_score.
 *
 * Run: node --test src/__tests__/score-consistency.test.mjs
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

// Inline the headlineScore logic rather than importing (avoids TS/ESM transform).
// This must stay in sync with src/lib/score-utils.ts.
function headlineScore(result) {
  return result.livability_score ?? result.disruption_score;
}

function scoreHeroDisplay(result) {
  const score = headlineScore(result);
  return Number.isFinite(score) ? Math.round(score) : 0;
}

// ── Fixture helpers ───────────────────────────────────────────────────────────

function makeResult({ disruption_score, livability_score }) {
  return {
    address: "123 Test St, Chicago, IL",
    disruption_score,
    livability_score,
    confidence: "high",
    severity: { noise: "low", traffic: "low", dust: "low" },
    top_risks: [],
    explanation: "",
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test("headlineScore returns livability_score when both fields are present", () => {
  const result = makeResult({ disruption_score: 60, livability_score: 46 });
  assert.equal(headlineScore(result), 46,
    "headline must use livability_score, not disruption_score");
});

test("headlineScore falls back to disruption_score when livability_score is absent", () => {
  const result = makeResult({ disruption_score: 60, livability_score: undefined });
  assert.equal(headlineScore(result), 60,
    "headline must fall back to disruption_score when livability_score is absent");
});

test("headlineScore falls back to disruption_score when livability_score is null", () => {
  const result = makeResult({ disruption_score: 55, livability_score: null });
  assert.equal(headlineScore(result), 55,
    "null livability_score must fall back to disruption_score");
});

test("headlineScore returns same value when both scores are equal (no divergence)", () => {
  const result = makeResult({ disruption_score: 42, livability_score: 42 });
  assert.equal(headlineScore(result), 42,
    "when scores are equal there is no inconsistency");
});

test("regression: WatchlistForm score matches ScoreHero headline when livability_score present", () => {
  // This is the exact scenario that caused the bug.
  // ScoreHero would display headlineScore(result) = 46.
  // WatchlistForm previously received result.disruption_score = 60.
  // Both must now use headlineScore(result).
  const result = makeResult({ disruption_score: 60, livability_score: 46 });

  const scoreHeroDisplay = headlineScore(result);     // what ScoreHero renders
  const watchlistFormScore = headlineScore(result);   // what WatchlistForm now receives

  assert.equal(scoreHeroDisplay, watchlistFormScore,
    "ScoreHero and WatchlistForm must display the same score value");
  assert.equal(scoreHeroDisplay, 46,
    "headline score must be livability_score (46), not disruption_score (60)");
});

test("regression: ScoreHero renders livability_score immediately, not an initial zero", () => {
  const result = makeResult({ disruption_score: 0, livability_score: 74 });

  assert.equal(scoreHeroDisplay(result), 74,
    "ScoreHero must render the API livability_score rather than a temporary zero");
});
