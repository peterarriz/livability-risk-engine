/**
 * Regression tests for user-facing score date formatting.
 *
 * The Node test runner does not transpile TS, so this mirrors the small public
 * contract in src/lib/date-format.ts and scans the score UI source for usage.
 */

import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatScoreDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:\b|[T ])/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day, 12, 0, 0, 0);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return `${MONTHS[month - 1]} ${day}, ${year}`;
}

function formatIsoDatesInText(text) {
  if (!text) return text ?? "";
  return text.replace(/\b(\d{4}-\d{2}-\d{2})(?:[T ][0-9:.+\-Z]+)?\b/g, (value) => (
    formatScoreDate(value) ?? value
  ));
}

test("date-only score dates use short US display without UTC day shifts", () => {
  assert.equal(formatScoreDate("2028-02-29"), "Feb 29, 2028");
  assert.equal(formatScoreDate("2026-05-29"), "May 29, 2026");
  assert.equal(formatScoreDate("2026-06-30"), "Jun 30, 2026");
  assert.equal(formatScoreDate("2026-07-29"), "Jul 29, 2026");
});

test("datetime-looking score dates are reduced to the source calendar day", () => {
  assert.equal(formatScoreDate("2028-02-29T00:00:00Z"), "Feb 29, 2028");
  assert.equal(formatIsoDatesInText("active through 2028-02-29T00:00:00Z"), "active through Feb 29, 2028");
});

test("missing or invalid dates do not throw or format", () => {
  assert.equal(formatScoreDate(null), null);
  assert.equal(formatScoreDate(undefined), null);
  assert.equal(formatScoreDate(""), null);
  assert.equal(formatScoreDate("not-a-date"), null);
  assert.equal(formatScoreDate("2028-02-31"), null);
});

test("score UI routes common backend date strings through the shared formatter", () => {
  const appWorkspace = read("../components/app-workspace.tsx");
  const scoreExperience = read("../components/score-experience.tsx");
  const mapView = read("../components/map-view.tsx");
  const textSanitize = read("../lib/text-sanitize.ts");

  assert.ok(appWorkspace.includes("formatIsoDatesInText(result.signal_summary)"));
  assert.ok(appWorkspace.includes("risk: formatIsoDatesInText(risk)"));
  assert.ok(scoreExperience.includes("formatIsoDatesInText(displayedRecommendation)"));
  assert.ok(scoreExperience.includes("formatIsoDatesInText(row.detail.display_title ?? row.detail.title)"));
  assert.ok(mapView.includes("formatScoreDateRange(s.start_date, s.end_date)"));
  assert.ok(textSanitize.includes("formatIsoDatesInText(result)"));
});
