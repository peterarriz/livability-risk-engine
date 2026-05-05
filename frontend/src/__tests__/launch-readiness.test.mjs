/**
 * Launch-readiness guardrails for the multi-city MVP demo.
 *
 * These tests intentionally scan public demo surfaces for stale Chicago-only
 * scope drift while preserving the approved Chicago reference demo examples.
 */

import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

function phrase(parts) {
  return parts.join("");
}

const publicDemoFiles = [
  "../app/page.tsx",
  "../app/bulk/page.tsx",
  "../components/app-workspace.tsx",
  "../app/api-docs/page.tsx",
  "../app/api-access/page.tsx",
  "../app/methodology/page.tsx",
  "../components/address-autocomplete.tsx",
  "../components/map-view.tsx",
  "../app/layout.tsx",
];

const publicCopyFiles = [
  "../app/page.tsx",
  "../app/pricing/page.tsx",
  "../app/api-docs/page.tsx",
  "../app/api-access/page.tsx",
  "../app/bulk/page.tsx",
  "../components/app-workspace.tsx",
];

test("public launch surfaces do not regress to Chicago-only scope", () => {
  const forbidden = [
    /Chicago-only/i,
    /Chicago MVP only/i,
    /scores Chicago addresses/i,
    /Search a Chicago address/i,
    /Enter a Chicago address/i,
    /pilot-evidence/i,
    /href="\/pricing"/i,
  ];

  for (const file of publicDemoFiles) {
    const text = read(file);
    for (const pattern of forbidden) {
      assert.ok(!pattern.test(text), `${file} contains stale launch-scope drift: ${pattern}`);
    }
  }
});

test("backend launch routes allow multi-city geocoding", () => {
  const backendLaunchFiles = [
    "../../../backend/app/routes/score.py",
    "../../../backend/app/routes/reports.py",
    "../../../backend/app/routes/keys.py",
  ];
  for (const file of backendLaunchFiles) {
    const text = read(file);
    assert.ok(!new RegExp(phrase(["Chicago addresses", " only"]), "i").test(text), `${file} rejects non-Chicago addresses`);
    assert.ok(!/launch demo only supports Chicago/i.test(text), `${file} contains stale Chicago-only error copy`);
  }
  const scoreRoute = read("../../../backend/app/routes/score.py");
  const reportsRoute = read("../../../backend/app/routes/reports.py");
  assert.ok(scoreRoute.includes("allow_national=True"));
  assert.ok(reportsRoute.includes("allow_national=True"));
});

test("approved high-risk demo wording stays aligned across backend and frontend", () => {
  const backendDeps = read("../../../backend/app/deps.py");
  const frontendApi = read("../lib/api.ts");
  const required = [
    "Traffic and curb access are the dominant near-term disruption signals at this address",
    "elevated short-term traffic and curb access disruption",
  ];

  for (const phrase of required) {
    assert.ok(backendDeps.includes(phrase), `backend demo missing: ${phrase}`);
    assert.ok(frontendApi.includes(phrase), `frontend demo missing: ${phrase}`);
  }
});

test("Next.js static chunks use framework-managed cache headers", () => {
  const nextConfig = read("../../next.config.mjs");
  assert.ok(!nextConfig.includes("/_next/static/:path*"));
});

test("out-of-scope product routes redirect away from launch demo", () => {
  const middleware = read("../../middleware.ts");
  for (const route of ["/pilot-evidence", "/portfolio", "/dashboard"]) {
    assert.ok(middleware.includes(`"${route}(.*)"`), `${route} is not launch-gated`);
  }
  for (const route of ["/pricing", "/neighborhood"]) {
    assert.ok(!middleware.includes(`"${route}(.*)"`), `${route} should stay reachable for prospect outreach`);
  }
  assert.ok(!middleware.includes('"/bulk(.*)"'), "/bulk should stay reachable so signed-out users can see the account prompt");
  assert.ok(middleware.includes('url.pathname = "/app"'));
});

test("/pricing renders pilot-stage access copy instead of a launch redirect", () => {
  const middleware = read("../../middleware.ts");
  const pricingPage = read("../app/pricing/page.tsx");

  assert.ok(!middleware.includes('"/pricing(.*)"'), "/pricing should not redirect to /app");
  assert.ok(pricingPage.includes("Access is by request during the design-partner pilot. Commercial pricing follows pilot validation."));
  assert.ok(pricingPage.includes("Public demos"));
  assert.ok(pricingPage.includes("Design-partner pilot"));
  assert.ok(pricingPage.includes("API / data partner access"));
  assert.ok(pricingPage.includes("Request pilot access"));
  assert.ok(pricingPage.includes("Try address scoring"));
  const stalePricingCopy = [
    phrase(["Free", " tier"]),
    phrase(["10", " lookups"]),
    phrase(["Upgrade", " to Pro"]),
    phrase(["un", "limited"]),
    phrase(["$", "49"]),
    phrase(["self-serve", " billing"]),
  ];
  for (const staleCopy of stalePricingCopy) {
    assert.ok(!pricingPage.includes(staleCopy), `/pricing contains stale pricing copy: ${staleCopy}`);
  }
});

test("public copy does not publish stale self-serve pricing or query-key API guidance", () => {
  const forbidden = [
    phrase(["Free", " tier"]),
    phrase(["10", " lookups/month"]),
    phrase(["10 address", " lookups"]),
    phrase(["$", "49"]),
    phrase(["Pro", " plan"]),
    phrase(["Unlimited", " lookups"]),
    phrase(["Upgrade your", " plan"]),
    phrase(["self-serve", " billing"]),
    phrase(["?", "api_key="]),
    phrase(["Chicago addresses", " only"]),
    phrase(["Chicago disruption", " scoring"]),
    phrase(["your-api", ".railway.app"]),
  ];

  for (const file of publicCopyFiles) {
    const text = read(file);
    for (const staleCopy of forbidden) {
      assert.ok(!text.includes(staleCopy), `${file} contains stale public copy: ${staleCopy}`);
    }
  }
});
