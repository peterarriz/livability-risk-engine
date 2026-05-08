/**
 * Source-level guardrails for the demo map polish.
 *
 * Leaflet positioning is browser-driven, so the unit harness cannot measure
 * pixels. These checks keep the intended stable map configuration in place.
 */

import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const mapView = read("../components/map-view.tsx");
const globals = read("../app/globals.css");

test("score map uses a readable unauthenticated light CARTO basemap", () => {
  assert.ok(mapView.includes("basemaps.cartocdn.com/light_all"));
  assert.ok(!mapView.includes("basemaps.cartocdn.com/dark_all"));
  assert.ok(mapView.includes("OpenStreetMap"));
  assert.ok(mapView.includes("CARTO"));
});

test("address label is a marker-anchored Leaflet tooltip, not an open detached popup", () => {
  assert.ok(mapView.includes("iconAnchor:"));
  assert.ok(mapView.includes("tooltipAnchor:"));
  assert.ok(mapView.includes("bindTooltip(escapeHtml(address)"));
  assert.ok(mapView.includes('className: "lre-address-tooltip"'));
  assert.ok(!mapView.includes("bindPopup(address).openPopup()"));
  assert.ok(globals.includes(".leaflet-container .lre-address-tooltip"));
});
