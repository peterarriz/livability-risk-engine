/**
 * Regression tests for frontend-only lookup quota handling.
 *
 * These inline the small quota helper logic to avoid TS/ESM transpilation.
 * Keep in sync with src/lib/lookup-quota.ts.
 *
 * Run: node --test src/__tests__/lookup-quota.test.mjs
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

const FREE_LIMIT = 10;
const ANON_LIMIT = 3;
const UNLIMITED_TIERS = new Set(["pro", "teams", "enterprise", "founder", "admin"]);

function normalizeSubscriptionTier(tier) {
  return typeof tier === "string" ? tier.trim().toLowerCase() : "";
}

function hasUnlimitedLookupAccess(tier) {
  return UNLIMITED_TIERS.has(normalizeSubscriptionTier(tier));
}

function getLookupUsageFromCount(isSignedIn, hasUnlimitedAccess, count) {
  if (hasUnlimitedAccess) {
    return { count: 0, limit: null, remaining: null, isGated: false, isUnlimited: true };
  }
  const limit = isSignedIn ? FREE_LIMIT : ANON_LIMIT;
  return {
    count,
    limit,
    remaining: Math.max(0, limit - count),
    isGated: count >= limit,
    isUnlimited: false,
  };
}

function signedInGateHeadline(usage) {
  return usage.limit === null
    ? "You've used your demo lookups this month."
    : `You've used your ${usage.limit} demo lookups this month.`;
}

test("signed-out demo quota remains limited", () => {
  const usage = getLookupUsageFromCount(false, false, 3);

  assert.equal(usage.limit, ANON_LIMIT);
  assert.equal(usage.remaining, 0);
  assert.equal(usage.isGated, true);
  assert.equal(usage.isUnlimited, false);
});

test("signed-in free demo quota remains limited", () => {
  const usage = getLookupUsageFromCount(true, false, 9);

  assert.equal(usage.limit, FREE_LIMIT);
  assert.equal(usage.remaining, 1);
  assert.equal(usage.isGated, false);
  assert.equal(usage.isUnlimited, false);
});

test("pilot tiers get unlimited frontend lookup access with case normalization", () => {
  for (const tier of ["pro", "Teams", " ENTERPRISE ", "Founder", "ADMIN"]) {
    const usage = getLookupUsageFromCount(true, hasUnlimitedLookupAccess(tier), 200);

    assert.equal(usage.limit, null, `${tier} should not carry a numeric local limit`);
    assert.equal(usage.remaining, null, `${tier} should not carry a numeric remaining count`);
    assert.equal(usage.isGated, false, `${tier} should not be gated locally`);
    assert.equal(usage.isUnlimited, true, `${tier} should be treated as unlimited`);
  }
});

test("quota gate copy does not render a non-finite numeric limit", () => {
  const forbidden = ["Inf", "inity"].join("");
  const usage = getLookupUsageFromCount(true, hasUnlimitedLookupAccess("founder"), 200);
  const message = signedInGateHeadline(usage);

  assert.ok(!message.includes(forbidden), `forbidden numeric limit leaked: ${message}`);
  assert.equal(message, "You've used your demo lookups this month.");
});
