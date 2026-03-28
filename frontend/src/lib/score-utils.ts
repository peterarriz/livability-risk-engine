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
