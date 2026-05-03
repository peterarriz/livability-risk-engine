import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function allowedTiersFromSource(source) {
  const match = source.match(/export const ALLOWED_BULK_TIERS = \[([\s\S]*?)\] as const;/);
  assert.ok(match, "ALLOWED_BULK_TIERS declaration should stay explicit");
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
}

function normalizeBulkTier(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : null;
}

test("/bulk no longer renders a browser API credential field", () => {
  const bulkPage = read("../app/bulk/page.tsx");

  assert.ok(!bulkPage.includes("/api/backend/score/batch/csv"), "/bulk should use the first-party bulk route");
  assert.ok(!bulkPage.includes("X-API-Key"), "/bulk should not send backend key headers from the browser");
  assert.ok(!/apiKey/i.test(bulkPage), "/bulk should not keep browser API key state");
  assert.ok(!/type="password"/.test(bulkPage), "/bulk should not render a password-style credential input");
});

test("/bulk signed-out and ineligible copy matches pilot account flow", () => {
  const bulkPage = read("../app/bulk/page.tsx");

  assert.ok(bulkPage.includes("Sign in to upload CSV"));
  assert.ok(bulkPage.includes("Public single-address scoring still works without sign-in"));
  assert.ok(bulkPage.includes("Bulk CSV scoring is available for pilot users"));
  assert.ok(bulkPage.includes("Request pilot access"));
});

test("/bulk recommends structured CSV columns while preserving address fallback", () => {
  const bulkPage = read("../app/bulk/page.tsx");

  assert.ok(bulkPage.includes("property_id,street_address,city,state,zip"), "sample CSV should use structured address columns");
  assert.ok(bulkPage.includes("ZIP is optional but helpful"), "copy should explain optional ZIP");
  assert.ok(bulkPage.includes("state should be a two-letter code"), "copy should guide state formatting");
  assert.ok(bulkPage.includes("Single-column <code className=\"bulk-code\">address</code> CSVs are still accepted"), "copy should preserve one-column address support");
  assert.ok(bulkPage.includes("Original columns are preserved where possible"), "results copy should mention preserved source columns");
});

test("bulk access tiers allow the approved pilot and internal account tiers", () => {
  const helper = read("../lib/bulk-access.ts");
  const tiers = new Set(allowedTiersFromSource(helper));
  const required = ["pilot", "pro", "teams", "enterprise", "founder", "admin"];

  for (const tier of required) {
    assert.ok(tiers.has(tier), `missing allowed bulk tier: ${tier}`);
    assert.ok(tiers.has(normalizeBulkTier(` ${tier.toUpperCase()} `)));
  }
});

test("bulk score route enforces auth, file upload, and server-only key config", () => {
  const route = read("../app/api/bulk/score-csv/route.ts");

  assert.ok(route.includes("await auth()"), "route should require Clerk auth");
  assert.ok(route.includes("Sign in to upload CSV."), "route should return signed-out copy");
  assert.ok(route.includes("formData.get(\"file\")"), "route should read the multipart file field");
  assert.ok(route.includes("Choose a CSV file before starting bulk scoring."), "route should reject missing file uploads");
  assert.ok(route.includes("LRE_INTERNAL_API_KEY"), "route should read a server-only internal key");
  assert.ok(!route.includes("NEXT_PUBLIC_LRE_INTERNAL_API_KEY"), "internal key must not be public-prefixed");
});
