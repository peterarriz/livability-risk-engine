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

// ---------------------------------------------------------------------------
// Recommended Action — decision-first guidance based on score + signals.
// ---------------------------------------------------------------------------

export type RecommendedAction = {
  icon: string;
  label: string;
  tone: "clear" | "monitor" | "review" | "defer";
};

type SignalLike = {
  end_date?: string | null;
};

/**
 * Derive a recommended action from the headline score and nearby signals.
 *
 * States:
 *   score < 30                          → Clear to proceed
 *   score 30-60, all signals end ≤ 30d  → Monitor (clearing soon)
 *   score 30-60, signals ongoing        → Review before committing
 *   score > 60                          → Defer if possible
 */
export function recommendedAction(
  score: number,
  signals: SignalLike[],
): RecommendedAction {
  if (score > 60) {
    // Find the latest end date for the "through [date]" label
    const latestEnd = _latestEndDate(signals);
    const throughLabel = latestEnd ? ` through ${_formatShortDate(latestEnd)}` : "";
    return {
      icon: "🔴",
      label: `Defer if possible — high disruption overlapping your target window${throughLabel}`,
      tone: "defer",
    };
  }

  if (score >= 30) {
    const latestEnd = _latestEndDate(signals);
    const daysUntilClear = latestEnd
      ? Math.ceil((latestEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      : null;

    if (daysUntilClear !== null && daysUntilClear <= 30 && daysUntilClear > 0) {
      return {
        icon: "📊",
        label: `Monitor — disruption clearing within ${daysUntilClear} days`,
        tone: "monitor",
      };
    }

    const throughLabel = latestEnd ? ` through ${_formatShortDate(latestEnd)}` : "";
    return {
      icon: "⚠",
      label: `Review before committing — active disruption${throughLabel}`,
      tone: "review",
    };
  }

  return {
    icon: "✓",
    label: "Clear to proceed — no active disruptions in your impact window",
    tone: "clear",
  };
}

function _latestEndDate(signals: SignalLike[]): Date | null {
  let latest: Date | null = null;
  for (const s of signals) {
    if (!s.end_date) continue;
    const d = new Date(s.end_date);
    if (isNaN(d.getTime())) continue;
    if (!latest || d > latest) latest = d;
  }
  return latest;
}

function _formatShortDate(d: Date): string {
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}
