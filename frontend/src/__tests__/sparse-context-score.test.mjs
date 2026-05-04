/**
 * Buyer-trust guardrails for sparse/contextual-only score pages.
 *
 * These tests scan the score UI source because the frontend test harness runs
 * under plain node without a TSX transform.
 */

import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const scoreExperience = read("../components/score-experience.tsx");
const appWorkspace = read("../components/app-workspace.tsx");
const apiTypes = read("../lib/api.ts");

test("contextual-only score pages show neighborhood context and manual-review copy", () => {
  assert.ok(scoreExperience.includes("Neighborhood context available"));
  assert.ok(scoreExperience.includes("Limited address-level coverage"));
  assert.ok(scoreExperience.includes("Review manually — limited address-level coverage"));
  assert.ok(scoreExperience.includes("We do not have address-level construction or closure signals for this block yet. This score reflects neighborhood context only."));
  assert.ok(scoreExperience.includes("contextualActionText(result.recommended_action)"));
});

test("neighborhood context panel exposes backend-provided sparse facts", () => {
  for (const field of [
    "fema_flood_zone",
    "flood_risk",
    "crime_trend",
    "crime_trend_pct",
    "crime_12mo",
    "median_income",
    "population",
    "vacancy_rate",
    "housing_age_med",
  ]) {
    assert.ok(apiTypes.includes(field), `ScoreResponse is missing ${field}`);
    assert.ok(scoreExperience.includes(field), `AreaContextPanel does not read ${field}`);
  }

  for (const label of [
    "FEMA flood zone",
    "Flood risk",
    "Crime trend",
    "Crime incidents (12 mo)",
    "Median income",
    "Population",
    "Vacancy rate",
    "Median housing age",
  ]) {
    assert.ok(scoreExperience.includes(label), `AreaContextPanel is missing ${label}`);
  }

  assert.ok(scoreExperience.includes("formatDollar(context.median_income)"));
  assert.ok(scoreExperience.includes("formatPercent(context.vacancy_rate)"));
  assert.ok(scoreExperience.includes("formatPercent(context.crime_trend_pct, { signed: true })"));
});

test("contextual-only area context appears before sparse no-signal explanation", () => {
  const areaContextIndex = appWorkspace.indexOf("hasAreaContext && isContextualOnlyResult");
  const quickExplanationIndex = appWorkspace.indexOf("<h2>Quick explanation</h2>");
  assert.ok(areaContextIndex > 0, "contextual area context panel is not rendered");
  assert.ok(quickExplanationIndex > 0, "quick explanation card is missing");
  assert.ok(areaContextIndex < quickExplanationIndex, "contextual area context should render before the sparse explanation");
});

test("severity chips and signal/confidence summaries are visible outside full analysis", () => {
  assert.ok(scoreExperience.includes("export function SeverityChips"));
  assert.ok(scoreExperience.includes('["Noise", severity.noise]'));
  assert.ok(scoreExperience.includes('["Traffic", severity.traffic]'));
  assert.ok(scoreExperience.includes('["Dust", severity.dust]'));
  assert.ok(scoreExperience.includes("{label}:"));
  assert.ok(scoreExperience.includes("confidence-reason-inline"));
  assert.ok(appWorkspace.includes("signal-summary-inline"));
  assert.ok(appWorkspace.includes("result.signal_summary"));
});

test("zero-signal mobile summaries do not turn top risks into fake signal pills", () => {
  assert.ok(scoreExperience.includes("if (addressSignalCount === 0) return []"));
  assert.ok(scoreExperience.includes("No address-level disruption signals found"));
});
