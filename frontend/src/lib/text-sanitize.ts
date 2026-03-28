/**
 * text-sanitize.ts
 *
 * Defence-in-depth sanitization layer for all text that comes from the API
 * and is rendered in user-facing sections (Why This Score, Signal Detail,
 * What This Means, signal card titles, permit notes, etc.).
 *
 * The backend applies the same mappings in backend/scoring/sanitize.py before
 * building explanation/risk strings. This module catches anything that slips
 * through (e.g. older records already in the DB, third-party enrichment).
 *
 * Keep WORK_TYPE_LABELS in sync with backend/scoring/sanitize.py.
 */

// ---------------------------------------------------------------------------
// Chicago CDOT street closure work_type code → human-readable label
// ---------------------------------------------------------------------------

const WORK_TYPE_LABELS: Record<string, string> = {
  GenOpening:        "general opening",
  GenOccupy:         "lane occupation",
  PartialClosure:    "partial lane closure",
  FullClosure:       "full street closure",
  Sidewalk:          "sidewalk work",
  CurbCut:           "curb cut",
  Curb:              "curb work",
  Dumpster:          "dumpster placement",
  StoragePod:        "storage pod",
  Crane:             "crane operation",
  Scaffold:          "scaffolding",
  Emergency:         "emergency work",
  Construction:      "construction work",
  RoadRepair:        "road repair",
  RoadResurfacing:   "road resurfacing",
  GasMain:           "gas main work",
  WaterMain:         "water main work",
  Sewer:             "sewer work",
  Electrical:        "electrical work",
  Filming:           "film/photo permit",
  SpecialEvent:      "special event",
  Festival:          "festival",
  Demonstration:     "demonstration",
  Moving:            "moving permit",
  TreeTrimming:      "tree trimming",
  StreetResurfacing: "street resurfacing",
  Excavation:        "excavation",
  Utility:           "utility work",
  PedestrianAccess:  "pedestrian access work",
  Loading:           "loading zone work",
  Parking:           "parking restriction",
  TrafficControl:    "traffic control",
  SignalWork:        "traffic signal work",
  StreetLight:       "street light work",
  WaterService:      "water service work",
  SewerRepair:       "sewer repair",
};

// Case-insensitive lookup
function lookupWorkType(code: string): string | null {
  if (WORK_TYPE_LABELS[code]) return WORK_TYPE_LABELS[code];
  // Try case-insensitive match
  const lower = code.toLowerCase();
  for (const [k, v] of Object.entries(WORK_TYPE_LABELS)) {
    if (k.toLowerCase() === lower) return v;
  }
  return null;
}

// ---------------------------------------------------------------------------
// CamelCase → readable fallback
// "RoadResurfacing" → "road resurfacing"
// ---------------------------------------------------------------------------

function camelToReadable(s: string): string {
  return s
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .toLowerCase()
    .trim();
}

// ---------------------------------------------------------------------------
// Parenthesized code replacement
// "(GenOpening)" → "(general opening)"
// ---------------------------------------------------------------------------

const PAREN_CODE_RE = /\(([A-Z][A-Za-z]+)\)/g;

function replaceParenCodes(text: string): string {
  return text.replace(PAREN_CODE_RE, (_, code: string) => {
    const label = lookupWorkType(code);
    if (label) return `(${label})`;
    // Try CamelCase split for unknown codes
    const readable = camelToReadable(code);
    return readable !== code.toLowerCase() ? `(${readable})` : `(${code})`;
  });
}

// ---------------------------------------------------------------------------
// ISO date replacement
// "2024-03-15" → "March 15, 2024"
// ---------------------------------------------------------------------------

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function formatIsoDate(iso: string): string {
  const parts = iso.slice(0, 10).split("-");
  if (parts.length !== 3) return iso;
  const [year, month, day] = parts;
  const monthIndex = parseInt(month, 10) - 1;
  if (monthIndex < 0 || monthIndex > 11) return iso;
  return `${MONTHS[monthIndex]} ${parseInt(day, 10)}, ${year}`;
}

const ISO_DATE_RE = /\b(\d{4}-\d{2}-\d{2})\b/g;

function replaceIsoDates(text: string): string {
  return text.replace(ISO_DATE_RE, (_, iso) => formatIsoDate(iso));
}

// ---------------------------------------------------------------------------
// Meter distance → feet
// "within roughly 120 meters" → "within roughly ~394 ft"
// "120 meters" → "~394 ft"
// ---------------------------------------------------------------------------

const METERS_RE = /\b(\d{1,5})\s*meters?\b/gi;

function replaceMeters(text: string): string {
  return text.replace(METERS_RE, (_, m) => `~${Math.round(Number(m) * 3.28084).toLocaleString()} ft`);
}

// ---------------------------------------------------------------------------
// Street range reformatting
// "HURON from 900 to 909" → "Huron between 900–909"
// ---------------------------------------------------------------------------

const RANGE_RE = /\b([A-Z0-9][A-Z0-9 ]{1,25})\s+from\s+(\d+)\s+to\s+(\d+)\b/gi;

function toTitleCase(s: string): string {
  return s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

function replaceRanges(text: string): string {
  return text.replace(RANGE_RE, (_, street, start, end) => {
    return `${toTitleCase(street.trim())} between ${start}–${end}`;
  });
}

// ---------------------------------------------------------------------------
// ALLCAPS normalization
// "EASY PERMIT PROGRAM at 123 N MAIN ST" → "Easy Permit Program at 123 N Main St"
// Only applied when the string is substantially uppercase.
// ---------------------------------------------------------------------------

function maybeDowncase(text: string): string {
  const upper = (text.match(/[A-Z]/g) ?? []).length;
  const alpha = (text.match(/[A-Za-z]/g) ?? []).length;
  if (alpha > 4 && upper / alpha > 0.7) {
    return toTitleCase(text);
  }
  return text;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Sanitize a single string from the API for safe user display.
 *
 * Applies in order:
 *   1. Parenthesized work type code replacement
 *   2. ISO date → "Month Day, Year"
 *   3. Meter distances → feet
 *   4. Street range reformatting
 *   5. ALLCAPS → Title Case (for predominantly-uppercase strings)
 */
export function sanitizeApiText(text: string | null | undefined): string {
  if (!text) return text ?? "";
  let result = replaceParenCodes(text);
  result = replaceIsoDates(result);
  result = replaceMeters(result);
  result = replaceRanges(result);
  result = maybeDowncase(result);
  return result.trim();
}

// Bare word code replacement (for notes that have "GenOpening; reason text")
const BARE_CODE_RE = new RegExp(
  `\\b(${Object.keys(WORK_TYPE_LABELS).join("|")})\\b`,
  "gi",
);

function replaceBareWordCodes(text: string): string {
  return text.replace(BARE_CODE_RE, (code: string) => {
    const label = lookupWorkType(code);
    return label ?? code;
  });
}

/**
 * Sanitize a notes/closure-reason string.
 * Notes may contain bare work_type codes (e.g. "GenOpening; reason text"),
 * so this also replaces unparenthesized codes.
 */
export function sanitizeNotes(text: string | null | undefined): string {
  if (!text) return text ?? "";
  let result = replaceParenCodes(text);
  result = replaceBareWordCodes(result);
  result = replaceIsoDates(result);
  return result.trim();
}
