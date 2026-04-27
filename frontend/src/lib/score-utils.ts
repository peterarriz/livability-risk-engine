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
  closure_full:          "Full road closure",
  closure_multi_lane:    "Road closure",
  closure_single_lane:   "Road closure",
  // Construction & demolition
  demolition:            "Demolition",
  construction:          "Construction",
  road_construction:     "Road construction",
  light_permit:          "Minor permit",
  // Utility
  utility:               "Utility work",
  utility_outage:        "Utility outage",
  utility_repair:        "Utility repair",
  // Traffic
  traffic_signal_outage: "Traffic signal outage",
  // Crime trends — collapsed to single label for legend
  crime_trend_increasing: "Crime trend",
  crime_trend_stable:     "Crime trend",
  crime_trend_decreasing: "Crime trend",
  // Other signals
  film_permit:           "Film permit",
  special_event:         "Special event",
  bike_station_outage:   "Bike station outage",
  pothole:               "Pothole report",
  water_main:            "Water main break",
  cave_in:               "Sinkhole",
  tree_emergency:        "Tree emergency",
  traffic_crash:         "Traffic incident",
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
 *   score >= 70                         → Ready to proceed
 *   score 30-60, all signals end ≤ 30d  → Monitor (clearing soon)
 *   score 30-60, signals ongoing        → Review before committing
 *   score > 60                          → Defer if possible
 */
export function recommendedAction(
  score: number,
  signals: SignalLike[],
): RecommendedAction {
  // Livability score: higher = better livability = less disruption.
  if (score >= 70) {
    return {
      icon: "\u2713",
      label: "Ready to proceed \u2014 no major disruptions visible in your impact window",
      tone: "clear",
    };
  }

  if (score >= 50) {
    return {
      icon: "\u26A0",
      label: "Proceed with awareness \u2014 minor nearby activity may affect access during business hours",
      tone: "review",
    };
  }

  if (score >= 30) {
    const latestEnd = _latestEndDate(signals);
    const daysUntilClear = latestEnd
      ? Math.ceil((latestEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      : null;

    if (daysUntilClear !== null && daysUntilClear <= 30 && daysUntilClear > 0) {
      return {
        icon: "\uD83D\uDCCA",
        label: `Monitor \u2014 disruption may clear within ${daysUntilClear} days`,
        tone: "monitor",
      };
    }

    const throughLabel = latestEnd ? ` through ${_formatShortDate(latestEnd)}` : "";
    return {
      icon: "\u26A0",
      label: `Schedule carefully \u2014 active disruption signals may affect access${throughLabel}`,
      tone: "review",
    };
  }

  // score < 30: high disruption
  const latestEnd = _latestEndDate(signals);
  const throughLabel = latestEnd ? ` through ${_formatShortDate(latestEnd)}` : "";
  return {
    icon: "\uD83D\uDD34",
    label: `Defer if possible \u2014 high disruption overlapping your target window${throughLabel}`,
    tone: "defer",
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
