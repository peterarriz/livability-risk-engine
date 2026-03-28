/**
 * Regression tests for the text sanitization layer.
 *
 * These tests guard against internal database codes / enum values appearing
 * in user-facing text.  The reported bug was:
 *   "HURON from 900 to 909 (GenOpening) closure" appearing in the
 *   explanation / signal card text.
 *
 * Run: node --test src/__tests__/text-sanitize.test.mjs
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

// Inline the sanitization logic to avoid TS/ESM transpilation.
// Must stay in sync with src/lib/text-sanitize.ts.

const WORK_TYPE_LABELS = {
  GenOpening: "general opening",
  GenOccupy: "lane occupation",
  PartialClosure: "partial lane closure",
  FullClosure: "full street closure",
  Sidewalk: "sidewalk work",
  CurbCut: "curb cut",
  Dumpster: "dumpster placement",
  Crane: "crane operation",
  Emergency: "emergency work",
  Construction: "construction work",
  RoadRepair: "road repair",
  Filming: "film/photo permit",
  SpecialEvent: "special event",
  Excavation: "excavation",
  Utility: "utility work",
};

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];

function formatIsoDate(iso) {
  const parts = iso.slice(0, 10).split("-");
  if (parts.length !== 3) return iso;
  const [year, month, day] = parts;
  const monthIndex = parseInt(month, 10) - 1;
  if (monthIndex < 0 || monthIndex > 11) return iso;
  return `${MONTHS[monthIndex]} ${parseInt(day, 10)}, ${year}`;
}

function camelToReadable(s) {
  return s.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2").toLowerCase().trim();
}

function replaceParenCodes(text) {
  return text.replace(/\(([A-Z][A-Za-z]+)\)/g, (_, code) => {
    const label = WORK_TYPE_LABELS[code] || WORK_TYPE_LABELS[code.toLowerCase()];
    if (label) return `(${label})`;
    const readable = camelToReadable(code);
    return readable !== code.toLowerCase() ? `(${readable})` : `(${code})`;
  });
}

function replaceIsoDates(text) {
  return text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (_, iso) => formatIsoDate(iso));
}

function replaceMeters(text) {
  return text.replace(/\b(\d{1,5})\s*meters?\b/gi, (_, m) =>
    `~${Math.round(Number(m) * 3.28084).toLocaleString()} ft`);
}

function toTitleCase(s) {
  return s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
}

function replaceRanges(text) {
  return text.replace(/\b([A-Z0-9][A-Z0-9 ]{1,25})\s+from\s+(\d+)\s+to\s+(\d+)\b/gi,
    (_, street, start, end) => `${toTitleCase(street.trim())} between ${start}–${end}`);
}

function maybeDowncase(text) {
  const upper = (text.match(/[A-Z]/g) ?? []).length;
  const alpha = (text.match(/[A-Za-z]/g) ?? []).length;
  if (alpha > 4 && upper / alpha > 0.7) return toTitleCase(text);
  return text;
}

function sanitizeApiText(text) {
  if (!text) return text ?? "";
  let r = replaceParenCodes(text);
  r = replaceIsoDates(r);
  r = replaceMeters(r);
  r = replaceRanges(r);
  r = maybeDowncase(r);
  return r.trim();
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test("regression: GenOpening code removed from explanation text", () => {
  const raw = "HURON from 900 to 909 (GenOpening) closure";
  const result = sanitizeApiText(raw);
  assert.ok(!result.includes("GenOpening"),
    `"GenOpening" should not appear in: ${result}`);
  assert.ok(result.includes("general opening"),
    `Expected "general opening" in: ${result}`);
});

test("regression: GenOccupy code replaced with readable label", () => {
  const raw = "Full street closure on W GRAND AVE from 123 to 199 (GenOccupy) closure";
  const result = sanitizeApiText(raw);
  assert.ok(!result.includes("GenOccupy"), `"GenOccupy" leaked: ${result}`);
  assert.ok(result.includes("lane occupation"), `Expected "lane occupation" in: ${result}`);
});

test("ISO dates in explanations are formatted as Month Day, Year", () => {
  const raw = "The active window runs through 2024-03-15.";
  const result = sanitizeApiText(raw);
  assert.ok(!result.includes("2024-03-15"), `ISO date leaked: ${result}`);
  assert.ok(result.includes("March 15, 2024"), `Expected formatted date in: ${result}`);
});

test("ISO dates at end of risk strings are formatted", () => {
  const raw = "Full street closure on Huron; active through 2024-08-31";
  const result = sanitizeApiText(raw);
  assert.ok(!result.includes("2024-08-31"), `ISO date leaked: ${result}`);
  assert.ok(result.includes("August 31, 2024"), `Expected "August 31, 2024" in: ${result}`);
});

test("meter distances converted to feet", () => {
  const raw = "within roughly 150 meters";
  const result = sanitizeApiText(raw);
  assert.ok(!result.match(/\d+\s*meters?/i), `meters leaked: ${result}`);
  assert.ok(result.includes("ft"), `Expected ft in: ${result}`);
});

test("street range notation reformatted", () => {
  const raw = "Full street closure on HURON from 900 to 909";
  const result = sanitizeApiText(raw);
  assert.ok(!result.match(/from \d+ to \d+/i), `Street range leaked: ${result}`);
  assert.ok(result.includes("between 900–909"), `Expected "between 900–909" in: ${result}`);
});

test("PartialClosure code replaced", () => {
  const raw = "Lane closure (PartialClosure) near Chicago Ave";
  const result = sanitizeApiText(raw);
  assert.ok(!result.includes("PartialClosure"), `PartialClosure leaked: ${result}`);
  assert.ok(result.includes("partial lane closure"), `Expected readable label in: ${result}`);
});

test("unknown CamelCase codes are split into readable words", () => {
  const raw = "Street work (RoadResurfacing) near your address";
  const result = replaceParenCodes(raw);
  assert.ok(!result.includes("RoadResurfacing"), `Unknown code leaked: ${result}`);
  assert.ok(result.includes("road resurfacing"), `Expected split words in: ${result}`);
});

test("plain text without codes is passed through unchanged", () => {
  const raw = "A nearby lane closure is the main driver of elevated disruption.";
  const result = sanitizeApiText(raw);
  // Should not alter normal prose
  assert.ok(result.includes("lane closure"), `Expected original text preserved: ${result}`);
  assert.ok(result.includes("main driver"), `Expected original text preserved: ${result}`);
});

test("null and undefined handled gracefully", () => {
  assert.equal(sanitizeApiText(null), "");
  assert.equal(sanitizeApiText(undefined), "");
  assert.equal(sanitizeApiText(""), "");
});

test("full explanation string end-to-end sanitization", () => {
  // Simulates what the backend would have generated before the fix
  const raw = "A nearby lane or street closure (HURON from 900 to 909 (GenOpening) closure, within roughly 85 meters) is the main driver, so this address has elevated short-term traffic disruption. The active window runs through 2024-06-30.";
  const result = sanitizeApiText(raw);

  assert.ok(!result.includes("GenOpening"), `GenOpening leaked`);
  assert.ok(!result.includes("2024-06-30"), `ISO date leaked`);
  assert.ok(!result.match(/\d+ meters/), `meters leaked`);
  assert.ok(result.includes("general opening"), `Expected readable work type`);
  assert.ok(result.includes("June 30, 2024"), `Expected formatted date`);
  assert.ok(result.includes("ft"), `Expected feet unit`);
});
