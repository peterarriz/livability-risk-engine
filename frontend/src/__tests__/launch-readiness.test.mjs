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

const publicDemoFiles = [
  "../app/page.tsx",
  "../components/app-workspace.tsx",
  "../app/api-docs/page.tsx",
  "../app/api-access/page.tsx",
  "../app/methodology/page.tsx",
  "../components/address-autocomplete.tsx",
  "../components/map-view.tsx",
  "../app/layout.tsx",
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
    assert.ok(!/Chicago addresses only/i.test(text), `${file} rejects non-Chicago addresses`);
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
  for (const route of ["/pricing", "/pilot-evidence", "/portfolio", "/dashboard", "/bulk"]) {
    assert.ok(middleware.includes(`"${route}(.*)"`), `${route} is not launch-gated`);
  }
  assert.ok(middleware.includes('url.pathname = "/app"'));
});
