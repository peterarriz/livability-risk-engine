/**
 * score-utils.ts — single source of truth for picking which numeric score
 * to display to users across all components and pages.
 *
 * Rule: when livability_score is present it is the canonical headline score
 * (composite, 0-100 scale). When absent, disruption_score is used as the
 * direct proxy. All UI components that show a headline score number MUST
 * call headlineScore() rather than reading fields directly — this prevents
 * the two fields from being rendered inconsistently on the same page.
 */

export type ScoreSource = {
  disruption_score: number;
  livability_score?: number | null;
};

/**
 * Returns the score value that should appear in all user-visible displays
 * for a given API result: livability_score when present, else disruption_score.
 */
export function headlineScore(result: ScoreSource): number {
  return result.livability_score ?? result.disruption_score;
}

// ---------------------------------------------------------------------------
// Impact type labels — single source of truth for all user-facing text.
// All components MUST call impactTypeLabel() instead of maintaining their
// own label maps. This prevents raw enum values like "closure_multi_lane"
// or "utility_outage" from leaking into user-facing text.
// ---------------------------------------------------------------------------

const IMPACT_TYPE_LABELS: Record<string, string> = {
  // Street closures
  closure_full:          "Full street closure",
  closure_multi_lane:    "Multi-lane closure",
  closure_single_lane:   "Lane / curb closure",
  // Construction & demolition
  demolition:            "Demolition / excavation",
  construction:          "Active construction",
  road_construction:     "Road construction",
  light_permit:          "Permitted work",
  // Utility
  utility:               "Utility work",
  utility_outage:        "Utility outage",
  utility_repair:        "Utility repair",
  // Traffic
  traffic_signal_outage: "Traffic signal outage",
  // Crime trends
  crime_trend_increasing: "Crime trend: increasing",
  crime_trend_stable:     "Crime trend: stable",
  crime_trend_decreasing: "Crime trend: decreasing",
  // Other signals
  film_permit:           "Film permit",
  special_event:         "Special event",
  bike_station_outage:   "Bike station outage",
  pothole:               "Pothole report",
  water_main:            "Water main break",
  cave_in:               "Cave-in / sinkhole",
  tree_emergency:        "Tree emergency",
  traffic_crash:         "Traffic crash",
  cta_service_alert:     "CTA service alert",
  flood_zone:            "Flood zone",
};

/**
 * Convert a raw impact_type enum to a user-friendly label.
 * Falls back to a cleaned-up version of the raw string (underscores → spaces,
 * title case) so unknown types never appear as raw enums.
 */
export function impactTypeLabel(impactType: string | null | undefined): string {
  if (!impactType) return "Unknown";
  const label = IMPACT_TYPE_LABELS[impactType];
  if (label) return label;
  // Fallback: "closure_multi_lane" → "Closure multi lane"
  return impactType.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
