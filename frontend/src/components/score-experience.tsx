"use client";

import { useEffect, useMemo, useRef, useState, FormEvent } from "react";

import { ApiError, detectNeighborhoodSlug, fetchCommute, fetchNeighborhood, fetchSuggestions, saveReport, subscribeWatch } from "@/lib/api";
import type {
  CommuteResponse,
  CommuteSignal,
  NeighborhoodResponse,
  NeighborhoodSlugInfo,
  ScoreHistoryEntry,
  ScoreResponse,
  SeverityLevel,
  TopRiskDetail,
  TrendDay,
  WatchResponse,
} from "@/lib/api";

type ScoreHeroProps = {
  result: ScoreResponse;
};

type SeverityMetersProps = {
  severity: ScoreResponse["severity"];
  confidence: ScoreResponse["confidence"];
  confidenceReasons: string[];
};

type TopRiskGridProps = {
  result: ScoreResponse;
};

type ExplanationPanelProps = {
  explanation: string;
  meaning: string[];
};

type ImpactWindowProps = {
  result: ScoreResponse;
};

type RiskCardModel = {
  id: string;
  eyebrow: string;
  title: string;
  distance: string | null;  // data-043: pre-formatted "~N ft away" string
  impact: "High" | "Medium" | "Low";
  signalDetail: string;     // "Signal detail" section: Claude description or rawText
  rationale: string;        // "Why this matters" section: Claude why_it_matters or heuristic
  evidence: string;
  chips: string[];
  rawText: string;          // original humanized text (fallback)
};

type TimelineSummary = {
  label: string;
  window: string;
  peak: string;
  progress: number;
};

const SEVERITY_PERCENT: Record<SeverityLevel, number> = {
  LOW: 32,
  MEDIUM: 66,
  HIGH: 100,
};

const SCORE_COPY = [
  { max: 24, label: "Low disruption risk", summary: "Near-term conditions look broadly stable around this address." },
  { max: 49, label: "Moderate disruption risk", summary: "Some friction is likely, but it should remain manageable." },
  { max: 74, label: "High disruption risk", summary: "Clear nearby activity is likely to affect access or daily experience." },
  { max: 100, label: "Severe disruption risk", summary: "Multiple strong signals point to meaningful short-term disruption." },
];

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function getScoreMessage(score: number) {
  return SCORE_COPY.find((entry) => score <= entry.max) ?? SCORE_COPY[SCORE_COPY.length - 1];
}

function normalizeSentence(text: string): string {
  return text.replace(/\.$/, "").trim();
}

function toTitleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function metersToFeet(meters: number): number {
  return Math.round(meters * 3.28084);
}

function humanizeRiskText(text: string): string {
  // Replace internal permit type codes with plain language
  let result = text
    .replace(/\bGenOpening\b/g, "Permitted work (opening phase)")
    .replace(/\bGenOccupy\b/g, "Active lane occupation");

  // Convert meter distances to feet
  result = result.replace(/(\d{1,4})\s*meters?\b/gi, (_, m) => `~${metersToFeet(Number(m))} ft`);

  // Humanize "18TH from 14 to 59" style street ranges → "18TH between addresses 14–59"
  result = result.replace(
    /\b([A-Z0-9][A-Z0-9\s]{1,20})\s+from\s+(\d+)\s+to\s+(\d+)\b/gi,
    (_, street, start, end) => `${toTitleCase(street.trim().toLowerCase())} between addresses ${start}–${end}`,
  );

  return result;
}

function inferImpact(text: string, index: number): RiskCardModel["impact"] {
  const normalized = text.toLowerCase();

  if (
    normalized.includes("dominant") ||
    normalized.includes("multi-lane") ||
    normalized.includes("2-lane") ||
    normalized.includes("closure") ||
    normalized.includes("adjacent")
  ) {
    return "High";
  }

  if (
    normalized.includes("extends") ||
    normalized.includes("through") ||
    normalized.includes("within roughly") ||
    normalized.includes("active") ||
    normalized.includes("near-term")
  ) {
    return "Medium";
  }

  return index === 0 ? "High" : "Low";
}

function inferDriverEyebrow(text: string): string {
  const normalized = text.toLowerCase();

  if (/closure|lane|traffic/.test(normalized)) return "Access signal";
  if (/construction|permit|site work|excavation|renovation/.test(normalized)) return "Worksite signal";
  if (/curb access|parking|loading|pickup|dropoff/.test(normalized)) return "Curb access";
  if (/through|window|next\s+\d+\s+days|active/.test(normalized)) return "Timing signal";
  return "Supporting signal";
}

function inferDriverTitle(text: string): string {
  const humanized = humanizeRiskText(text);
  const normalized = normalizeSentence(humanized);
  const simplified = normalized
    .replace(/^active\s+/i, "")
    .replace(/^a nearby\s+/i, "")
    .replace(/^nearby\s+/i, "")
    .replace(/^traffic and curb access are the dominant near-term disruption signals at this address$/i, "Traffic and curb access drive this score")
    .replace(/\bwithin roughly\b/gi, "~")
    .replace(/\s+/g, " ");

  if (simplified.length <= 76) {
    return simplified;
  }

  const firstClause = simplified.split(/,| so | because /i)[0]?.trim();
  return firstClause && firstClause.length >= 20 ? firstClause : simplified;
}

function deriveDriverRationale(text: string): string {
  const normalized = text.toLowerCase();
  const meterMatch = text.match(/(\d{1,4})\s*meters?/i);
  const distanceLabel = meterMatch ? `~${metersToFeet(Number(meterMatch[1]))} ft away` : "nearby";

  if (/2-lane|multi-lane/.test(normalized) && /closure/.test(normalized)) {
    return `A multi-lane closure ${distanceLabel} reduces available travel lanes and can affect access during the active window.`;
  }
  if (/closure|lane/.test(normalized) && !/through|window/.test(normalized)) {
    return `This lane restriction ${distanceLabel} affects normal traffic flow and curb access near the address.`;
  }
  if (/dominant|traffic.*signal|curb.*dominant/.test(normalized)) {
    return "Traffic and curb conditions are the primary factor elevating the disruption score at this address.";
  }
  if (/through|window|days|months|timeline/.test(normalized)) {
    return "A defined active window helps you plan around the disruption with more confidence.";
  }
  if (/within roughly|adjacent|close proximity/.test(normalized)) {
    return `At ${distanceLabel}, this signal is close enough to directly affect arrivals and departures.`;
  }
  if (/permit|construction|site work|excavation|renovation/.test(normalized)) {
    return "Active permitted work nearby provides a concrete physical basis for the elevated disruption level.";
  }
  if (/curb access|parking|loading|pickup|dropoff/.test(normalized)) {
    return "Curb friction typically appears before broader congestion and can affect arrival quality quickly.";
  }

  return "This signal contributes meaningfully to the overall disruption read for this address.";
}

function inferDataSource(text: string): string {
  const normalized = text.toLowerCase();
  if (/closure|lane|cdot|street closing/.test(normalized)) {
    return "Source: CDOT street closure data";
  }
  if (/permit|construction|site work|excavation|renovation|genopening|genoccupy/i.test(normalized)) {
    return "Source: City of Chicago building permit data";
  }
  return "Source: City of Chicago Open Data Portal";
}

function extractRiskChips(text: string, impact: RiskCardModel["impact"]): string[] {
  const chips = new Set<string>([`${impact} impact`]);
  const normalized = text.toLowerCase();

  const meterMatch = text.match(/(\d{1,4})\s*meters?/i);
  if (meterMatch) {
    chips.add(`~${metersToFeet(Number(meterMatch[1]))} ft away`);
  }

  const dateMatch = text.match(/(20\d{2}-\d{2}-\d{2})/);
  if (dateMatch) {
    chips.add(`Active through ${dateMatch[1]}`);
  }

  const nextDaysMatch = text.match(/next\s+(\d{1,3})\s+days/i);
  if (nextDaysMatch) {
    chips.add(`${nextDaysMatch[1]} day window`);
  }

  if (/closure|lane/.test(normalized)) chips.add("Road access");
  if (/construction|permit|site work|renovation|excavation/.test(normalized)) chips.add("Construction");
  if (/curb access|parking|loading|pickup|dropoff/.test(normalized)) chips.add("Curb access");

  return Array.from(chips).slice(0, 4);
}

function buildRiskCards(result: ScoreResponse): RiskCardModel[] {
  return result.top_risks.slice(0, 3).map((risk, index) => {
    const humanized = humanizeRiskText(risk);
    const impact = inferImpact(humanized, index);

    // data-043: prefer the richer 4-field display card when available.
    // Falls back through: display_title → rewritten_title → heuristic.
    // top_risk_details is parallel to top_risks (same index order).
    const detail = result.top_risk_details?.[index];
    const displayTitle = detail?.display_title ?? detail?.rewritten_title ?? null;
    const description = detail?.description ?? detail?.rewritten_description ?? null;
    const whyItMatters = detail?.why_it_matters ?? null;
    const distanceLabel = detail?.distance ?? null;

    return {
      id: `${risk}-${index}`,
      eyebrow: inferDriverEyebrow(humanized),
      title: displayTitle ?? inferDriverTitle(humanized),
      distance: distanceLabel,
      impact,
      // "Signal detail" section: use Claude description, fall back to rawText
      signalDetail: description ?? humanized,
      // "Why this matters" section: use Claude why_it_matters, fall back to heuristic
      rationale: whyItMatters ?? description ?? deriveDriverRationale(humanized),
      evidence: inferDataSource(risk),
      chips: extractRiskChips(humanized, impact),
      rawText: humanized,
    };
  });
}

function inferConfidenceReasons(result: ScoreResponse): string[] {
  const reasons: string[] = [];
  const combinedText = [...result.top_risks, result.explanation].join(" ").toLowerCase();

  if (result.top_risks.length >= 3) {
    reasons.push("Multiple nearby signals reinforce the score.");
  } else if (result.top_risks.length === 2) {
    reasons.push("More than one supporting signal is present.");
  } else {
    reasons.push("The score is driven by a small number of visible signals.");
  }

  if (/through\s+\d{4}-\d{2}-\d{2}|next\s+\d+\s+days|active\s+closure\s+window|window/i.test(combinedText)) {
    reasons.push("Timing is specific enough to indicate an active disruption window.");
  }

  if (/within roughly|meters|adjacent|address/i.test(combinedText)) {
    reasons.push("At least one signal is closely tied to the address.");
  }

  if (result.confidence === "HIGH") {
    reasons.push("Evidence is specific enough for a high-confidence read.");
  } else if (result.confidence === "MEDIUM") {
    reasons.push("Evidence is credible, but still directional rather than exact site truth.");
  } else {
    reasons.push("Evidence should be treated as directional until stronger confirmation appears.");
  }

  return reasons.slice(0, 3);
}

function inferMeaning(result: ScoreResponse): string[] {
  const insights: string[] = [];
  const combinedText = [...result.top_risks, result.explanation].join(" ").toLowerCase();

  if (result.severity.traffic === "HIGH" || /closure|traffic|curb access|parking|loading/i.test(combinedText)) {
    insights.push("Expect slower arrivals, pickup friction, or weaker curb access during the active window.");
  }

  if (result.severity.noise !== "LOW" || /noise|construction|renovation|site work/i.test(combinedText)) {
    insights.push(
      result.severity.noise === "HIGH"
        ? "Daytime construction noise is likely to be consistently noticeable near the address."
        : "Some daytime construction noise is possible, but it is not the dominant issue here."
    );
  }

  if (result.severity.dust === "HIGH" || /dust|excavation|demolition|vibration/i.test(combinedText)) {
    insights.push("Excavation or site activity may create localized dust or vibration sensitivity.");
  }

  if (insights.length === 0) {
    insights.push("Available city signals suggest normal day-to-day access for most visits in the near term.");
  }

  return insights.slice(0, 3);
}

function parseDateString(value: string): Date | null {
  const match = value.match(/(20\d{2})-(\d{2})-(\d{2})/);
  if (!match) {
    return null;
  }

  const [, year, month, day] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(date: Date): string {
  return `${MONTH_NAMES[date.getUTCMonth()]} ${date.getUTCDate()}, ${date.getUTCFullYear()}`;
}

function formatMonthYear(date: Date): string {
  return `${MONTH_NAMES[date.getUTCMonth()]} ${date.getUTCFullYear()}`;
}

function buildTimelineSummary(result: ScoreResponse): TimelineSummary {
  const combinedText = [...result.top_risks, result.explanation].join(" ");
  const dateMatches = [...combinedText.matchAll(/20\d{2}-\d{2}-\d{2}/g)].map((match) => match[0]);
  const parsedDates = dateMatches
    .map((value) => parseDateString(value))
    .filter((value): value is Date => value instanceof Date)
    .sort((left, right) => left.getTime() - right.getTime());

  if (parsedDates.length > 0) {
    const now = new Date();
    const latest = parsedDates[parsedDates.length - 1];
    const diffDays = Math.max(0, Math.ceil((latest.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
    return {
      label: `${formatDate(now)} → ${formatDate(latest)}`,
      window: `Current signal window runs through ${formatMonthYear(latest)}.`,
      peak:
        diffDays <= 30
          ? "Most relevant right now."
          : diffDays <= 90
            ? "Most relevant over the next one to three months."
            : "Monitor for a longer active window. ",
      progress: Math.min(100, Math.max(18, 100 - diffDays / 2)),
    };
  }

  const horizonMatch = combinedText.match(/next\s+(\d{1,3})\s+days/i);
  if (horizonMatch) {
    const days = Number(horizonMatch[1]);
    return {
      label: `Now → next ${days} days`,
      window: `Signals indicate activity over roughly the next ${days} days.`,
      peak: days <= 90 ? "Most relevant in the current planning window." : "Worth monitoring beyond the immediate planning window.",
      progress: Math.min(100, Math.max(24, days)),
    };
  }

  return {
    label: "Near-term activity window",
    window: "The response points to near-term activity, but without a precise end date.",
    peak: "Focus on the strongest active driver.",
    progress: 42,
  };
}

function useAnimatedScore(target: number) {
  const [displayScore, setDisplayScore] = useState(0);

  useEffect(() => {
    let frame = 0;
    const durationMs = 700;
    const startedAt = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startedAt;
      const progress = Math.min(elapsed / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayScore(Math.round(target * eased));

      if (progress < 1) {
        frame = window.requestAnimationFrame(tick);
      }
    };

    frame = window.requestAnimationFrame(tick);

    return () => window.cancelAnimationFrame(frame);
  }, [target]);

  return displayScore;
}

function getGaugeBand(score: number): "low" | "moderate" | "high" {
  if (score <= 30) return "low";
  if (score <= 60) return "moderate";
  return "high";
}

function getBenchmarkText(score: number): string {
  if (score < 20) return "This address scores below the typical Chicago range of 20–40.";
  if (score <= 40) return "This address falls within the typical Chicago range of 20–40.";
  return "This address scores above the typical Chicago range of 20–40.";
}

export function ScoreHero({ result }: ScoreHeroProps) {
  const headlineScore = result.livability_score ?? result.disruption_score;
  const displayScore = useAnimatedScore(headlineScore);
  const scoreMessage = getScoreMessage(headlineScore);
  const timeline = useMemo(() => buildTimelineSummary(result), [result]);
  const isDemo = result.mode === "demo";
  const modeLabel = isDemo ? "Limited data coverage" : "Live Chicago signal";
  const modeLabelTooltip = isDemo
    ? "Live permit data may not be available for this address. Score is estimated from nearby signals."
    : undefined;
  const gaugeBand = getGaugeBand(headlineScore);
  const breakdown = result.livability_breakdown?.components ?? {};

  return (
    <div className="score-hero">
      <div className="score-hero-copy">
        <p className="score-hero-kicker">Headline assessment</p>
        <div className="score-hero-topline">
          <p className="score-label">Livability Score</p>
          <p className="confidence-pill" title={modeLabelTooltip}>{modeLabel}</p>
        </div>
        <div className="score-value score-value--animated">{displayScore}</div>

        <div className="score-gauge" aria-label={`Score ${displayScore} out of 100`}>
          <div className="score-gauge-track">
            <div className={`score-gauge-fill score-gauge-fill--${gaugeBand}`} style={{ width: `${displayScore}%` }} />
            <div className="score-gauge-marker" style={{ left: "30%" }} aria-hidden="true" />
            <div className="score-gauge-marker" style={{ left: "60%" }} aria-hidden="true" />
          </div>
          <div className="score-gauge-labels" aria-hidden="true">
            <span>0 — Low</span>
            <span>30</span>
            <span>60</span>
            <span>100 — High</span>
          </div>
        </div>
        <p className="score-benchmark">{getBenchmarkText(headlineScore)}</p>

        <h2 className="score-hero-title">{scoreMessage.label}</h2>
        <p className="score-hero-summary">{scoreMessage.summary}</p>
      </div>

      <div className="score-hero-sidecar">
        <p className="score-meta">Address assessed</p>
        <p className="score-hero-address">{result.address}</p>
        <div className="score-hero-meta-stack">
          <div>
            <span>Confidence</span>
            <strong>{toTitleCase(result.confidence.toLowerCase())}</strong>
          </div>
          <div>
            <span>Impact window</span>
            <strong>{timeline.label}</strong>
          </div>
          <div>
            <span>Primary signals</span>
            <strong>{result.top_risks.length} detected</strong>
          </div>
          <div>
            <span>Disruption score</span>
            <strong>{result.disruption_score}</strong>
          </div>
        </div>
        {Object.keys(breakdown).length > 0 && (
          <div className="score-hero-meta-stack" style={{ marginTop: "0.75rem" }}>
            {Object.entries(breakdown).map(([k, v]) => (
              <div key={k}>
                <span>{k.replace(/_/g, " ")}</span>
                <strong>{v.weighted_contribution.toFixed(1)} pts</strong>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function SeverityMeters({ severity, confidence, confidenceReasons }: SeverityMetersProps) {
  const rows = useMemo(
    () => [
      { label: "Signal noise (unrelated activity nearby)", value: severity.noise, accent: "noise" },
      { label: "Access disruption", value: severity.traffic, accent: "traffic" },
      { label: "Construction intensity", value: severity.dust, accent: "dust" },
    ],
    [severity],
  );

  return (
    <div className="severity-stack">
      <div className="confidence-summary">
        <div className="confidence-summary-head">
          <p className="confidence-summary-label">
            Confidence
            <span className="tooltip-anchor" tabIndex={0} aria-label="About confidence scoring">
              ?
              <span className="tooltip-content" role="tooltip">
                Confidence reflects how closely the detected signals are tied to this specific address, not how severe the disruption is.
              </span>
            </span>
          </p>
          <strong>{toTitleCase(confidence.toLowerCase())}</strong>
        </div>
        <ul className="confidence-reason-list">
          {confidenceReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

      <div className="severity-grid">
        {rows.map((row) => (
          <div key={row.label} className="severity-row">
            <div className="severity-row-head">
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
            <div className="severity-meter" aria-hidden="true">
              <div
                className={`severity-meter-fill severity-meter-fill--${row.accent}`}
                style={{ width: `${SEVERITY_PERCENT[row.value]}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const IMPACT_TYPE_LABELS: Record<string, string> = {
  closure_full: "Full street closure",
  closure_multi_lane: "Multi-lane closure",
  closure_single_lane: "Single-lane closure",
  demolition: "Demolition / excavation",
  construction: "Construction permit",
  light_permit: "Light permit",
};

const SOURCE_LABELS: Record<string, string> = {
  chicago_closures: "CDOT Street Closures",
  chicago_permits: "Chicago Building Permits",
};

function PermitDetailPanel({ detail, onClose }: { detail: TopRiskDetail; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  function formatDate(iso: string | null): string {
    if (!iso) return "Unknown";
    const [year, month, day] = iso.split("-");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[Number(month) - 1]} ${Number(day)}, ${year}`;
  }

  return (
    <div ref={ref} className="permit-detail-panel" role="region" aria-label="Permit details">
      <div className="permit-detail-head">
        <p className="permit-detail-label">Permit / closure detail</p>
        <button type="button" className="permit-detail-close" onClick={onClose} aria-label="Close details">×</button>
      </div>

      {/* data-043: show Claude-generated display card at the top when available */}
      {(detail.display_title || detail.description || detail.why_it_matters) && (
        <div className="permit-detail-summary">
          {detail.display_title && (
            <p className="permit-detail-summary-title">{detail.display_title}</p>
          )}
          {detail.distance && (
            <p className="permit-detail-summary-distance">{detail.distance}</p>
          )}
          {detail.description && (
            <p className="permit-detail-summary-desc">{detail.description}</p>
          )}
          {detail.why_it_matters && (
            <p className="permit-detail-summary-why">
              <strong>Why it matters:</strong> {detail.why_it_matters}
            </p>
          )}
        </div>
      )}

      <dl className="permit-detail-dl">
        <div>
          <dt>Project ID</dt>
          <dd className="permit-detail-id">{detail.project_id}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{SOURCE_LABELS[detail.source] ?? detail.source}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{IMPACT_TYPE_LABELS[detail.impact_type] ?? detail.impact_type}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd className={`permit-status permit-status--${detail.status}`}>{detail.status}</dd>
        </div>
        {detail.notes && (
          <div>
            <dt>Notes</dt>
            <dd>{detail.notes}</dd>
          </div>
        )}
        {detail.address && (
          <div>
            <dt>Location</dt>
            <dd>{detail.address}</dd>
          </div>
        )}
        <div>
          <dt>Distance from address</dt>
          <dd>~{detail.distance_m.toLocaleString()} m ({Math.round(detail.distance_m * 3.28084).toLocaleString()} ft)</dd>
        </div>
        <div>
          <dt>Start date</dt>
          <dd>{formatDate(detail.start_date)}</dd>
        </div>
        <div>
          <dt>End date</dt>
          <dd>{formatDate(detail.end_date)}</dd>
        </div>
        <div>
          <dt>Weighted contribution</dt>
          <dd>{detail.weighted_score} pts</dd>
        </div>
      </dl>
    </div>
  );
}

export function TopRiskGrid({ result }: TopRiskGridProps) {
  const riskCards = useMemo(() => buildRiskCards(result), [result]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const expandedCard = riskCards.find((r) => r.id === expandedId) ?? null;

  function toggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  if (riskCards.length === 0) {
    return (
      <div className="risk-no-signals">
        <p className="risk-no-signals-kicker">No disruptions detected</p>
        <p>No active construction or closure signals were found near this address at the time of lookup. The surrounding area appears clear for the current planning window.</p>
      </div>
    );
  }

  const colClass = riskCards.length < 3 ? ` risk-card-grid--${riskCards.length}col` : "";

  return (
    <div className="risk-card-section">
      <div className={`risk-card-grid${colClass}`}>
        {riskCards.map((risk, index) => {
          const isOpen = expandedId === risk.id;
          return (
            <article
              key={risk.id}
              className={`risk-card card-entrance${isOpen ? " risk-card--active" : ""}`}
              style={{ animationDelay: `${index * 90}ms` }}
            >
              <div className="risk-card-head">
                <div className="risk-card-head-text">
                  <p className="risk-card-index">{risk.eyebrow}</p>
                  <h3>{risk.title}</h3>
                </div>
                <span className={`impact-badge impact-badge--${risk.impact.toLowerCase()}`}>{risk.impact}</span>
              </div>

              <div className="risk-chip-row" aria-label="Driver metadata">
                {risk.chips.map((chip) => (
                  <span key={chip} className="risk-chip">
                    {chip}
                  </span>
                ))}
              </div>

              <button
                type="button"
                className="risk-card-expand-btn"
                onClick={() => toggle(risk.id)}
                aria-expanded={isOpen}
                aria-controls={`risk-detail-${index}`}
              >
                {isOpen ? "Hide detail ↑" : "Show detail ↓"}
              </button>
            </article>
          );
        })}
      </div>

      {expandedCard && (
        <div
          className="risk-card-detail card-entrance"
          id={`risk-detail-${riskCards.findIndex((r) => r.id === expandedCard.id)}`}
          role="region"
          aria-label={`Detail for ${expandedCard.eyebrow}`}
        >
          <div className="risk-detail-header">
            <div>
              <p className="risk-card-index">{expandedCard.eyebrow}</p>
              <h3 className="risk-detail-title">{expandedCard.title}</h3>
            </div>
            <span className={`impact-badge impact-badge--${expandedCard.impact.toLowerCase()}`}>
              {expandedCard.impact} impact
            </span>
          </div>

          <div className="risk-detail-body">
            <div className="risk-detail-section">
              <p className="risk-detail-label">Signal detail</p>
              <p className="risk-detail-text">{expandedCard.signalDetail}</p>
            </div>

            <div className="risk-detail-section">
              <p className="risk-detail-label">Why this matters</p>
              <p className="risk-detail-text">{expandedCard.rationale}</p>
            </div>

            <div className="risk-detail-section">
              <p className="risk-detail-label">Data source</p>
              <p className="risk-detail-text">{expandedCard.evidence}</p>
            </div>
          </div>

          <button
            type="button"
            className="risk-detail-close"
            onClick={() => setExpandedId(null)}
          >
            Close ✕
          </button>
        </div>
      )}
    </div>
  );
}

export function ExplanationPanel({ explanation, meaning }: ExplanationPanelProps) {
  return (
    <div className="explanation-stack">
      <div className="explanation-panel card-entrance" style={{ animationDelay: "180ms" }}>
        <p className="explanation-kicker">Why this score</p>
        <p className="explanation-copy">{explanation}</p>
      </div>

      <div className="meaning-panel card-entrance" style={{ animationDelay: "240ms" }}>
        <p className="explanation-kicker">What this means</p>
        <ul className="meaning-list">
          {meaning.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function ImpactWindow({ result }: ImpactWindowProps) {
  const timeline = useMemo(() => buildTimelineSummary(result), [result]);

  return (
    <div className="impact-window card-entrance" style={{ animationDelay: "120ms" }}>
      <div className="impact-window-head">
        <div>
          <p className="impact-window-kicker">Timeline</p>
          <h3>Active window</h3>
        </div>
        <span className="impact-window-label">{timeline.label}</span>
      </div>
      <div className="impact-window-bar" aria-hidden="true">
        <div className="impact-window-bar-fill" style={{ width: `${timeline.progress}%` }} />
      </div>
      <p className="impact-window-copy">{timeline.window}</p>
      <p className="impact-window-peak">{timeline.peak}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScoreSparkline  (data-025, enhanced)
// 200×44 SVG line chart with:
//   • Gradient area fill below the line
//   • Dashed horizontal reference at Chicago average (35)
//   • Distinct "today" dot on the current score (rightmost point)
//   • Week-over-week trend label: "Up X pts this week" / "Down X pts" / "Stable"
// ---------------------------------------------------------------------------

const CHICAGO_AVG = 35;
const DAY_MS = 86_400_000;

type ScoreSparklineProps = {
  history: ScoreHistoryEntry[];
  currentScore: number;
};

let _sparklineCounter = 0;

export function ScoreSparkline({ history, currentScore }: ScoreSparklineProps) {
  // Stable unique id so the SVG gradient doesn't collide when two sparklines
  // appear on the same page (score card + neighbourhood context card).
  const gradId = useMemo(() => `spark-fill-${++_sparklineCounter}`, []);
  const derived = useMemo(() => {
    const now = Date.now();
    const cutoff30 = now - 30 * DAY_MS;

    // Sort chronologically; drop entries older than 30 days.
    const dated = history
      .filter((e) => e.created_at != null)
      .map((e) => ({ score: e.disruption_score, ts: new Date(e.created_at!).getTime() }))
      .filter((e) => e.ts >= cutoff30)
      .sort((a, b) => a.ts - b.ts);

    // Undated entries (created_at null) spread across the window as fallback.
    const undated = history
      .filter((e) => e.created_at == null)
      .map((e, i, arr) => ({
        score: e.disruption_score,
        ts: cutoff30 + ((i + 1) / (arr.length + 1)) * (30 * DAY_MS),
      }));

    const historical = [...undated, ...dated].sort((a, b) => a.ts - b.ts);

    // Always append the live current score as "now".
    const all = [...historical, { score: currentScore, ts: now }];
    if (all.length < 2) return null;

    // Week trend: compare current score vs the oldest entry >= 5 days old.
    const fiveDaysAgo = now - 5 * DAY_MS;
    const weekRef = historical.filter((e) => e.ts <= fiveDaysAgo).at(-1);
    const weekDelta = weekRef != null ? currentScore - weekRef.score : null;

    return { points: all.map((e) => e.score), weekDelta, count: all.length };
  }, [history, currentScore]);

  if (!derived) return null;

  const { points, weekDelta, count } = derived;

  // ── SVG layout ────────────────────────────────────────────────
  const W = 200;
  const H = 44;
  const PX = 6;   // horizontal pad
  const PY = 5;   // vertical pad
  const innerW = W - PX * 2;
  const innerH = H - PY * 2;

  const minVal = Math.max(0,   Math.min(...points, CHICAGO_AVG) - 6);
  const maxVal = Math.min(100, Math.max(...points, CHICAGO_AVG) + 6);
  const range  = maxVal - minVal || 1;

  const toX = (i: number) => PX + (i / (points.length - 1)) * innerW;
  const toY = (v: number) => PY + (1 - (v - minVal) / range) * innerH;

  // Line path
  const linePath = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
    .join(" ");

  // Closed area path (line + bottom edge)
  const areaPath =
    linePath +
    ` L${toX(points.length - 1).toFixed(1)},${H} L${PX},${H} Z`;

  // Chicago avg line
  const avgY   = toY(CHICAGO_AVG);
  const todayX = toX(points.length - 1);
  const todayY = toY(points[points.length - 1]);

  // Dot color: match score band
  const dotColor =
    currentScore >= 81 ? "#7c3aed" :
    currentScore >= 61 ? "#ef4444" :
    currentScore >= 41 ? "#f59e0b" :
    currentScore >= 21 ? "#3ce5b3" :
                         "#10b981";

  // Trend label
  let trendLabel: string;
  let trendColor: string;
  if (weekDelta === null || Math.abs(weekDelta) <= 2) {
    trendLabel = "→ Stable this week";
    trendColor = "#94a3b8";
  } else if (weekDelta > 0) {
    trendLabel = `↑ Up ${weekDelta} pts this week`;
    trendColor = "#ef4444";
  } else {
    trendLabel = `↓ Down ${Math.abs(weekDelta)} pts this week`;
    trendColor = "#10b981";
  }

  return (
    <div
      className="sparkline-wrapper"
      aria-label={`Score history over ${count} readings. ${trendLabel}.`}
    >
      {/* Header row */}
      <div className="sparkline-header">
        <span className="sparkline-label">Score history · 30 days</span>
        <span className="sparkline-trend" style={{ color: trendColor }}>
          {trendLabel}
        </span>
      </div>

      {/* SVG chart */}
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="sparkline-svg"
        aria-hidden="true"
        style={{ display: "block", overflow: "visible" }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#84a6ff" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#84a6ff" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Area fill */}
        <path d={areaPath} fill={`url(#${gradId})`} />

        {/* Line */}
        <path
          d={linePath}
          fill="none"
          stroke="#84a6ff"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Chicago average dashed reference line */}
        <line
          x1={PX}
          y1={avgY.toFixed(1)}
          x2={W - PX}
          y2={avgY.toFixed(1)}
          stroke="rgba(148,163,184,0.45)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        {/* "35" label at right edge of avg line */}
        <text
          x={W - PX + 1}
          y={(avgY + 3.5).toFixed(1)}
          fontSize="7"
          fill="rgba(148,163,184,0.7)"
          textAnchor="start"
          fontFamily="system-ui, sans-serif"
        >
          35
        </text>

        {/* Today dot — outer ring */}
        <circle
          cx={todayX.toFixed(1)}
          cy={todayY.toFixed(1)}
          r="5"
          fill={dotColor}
          fillOpacity="0.2"
        />
        {/* Today dot — inner solid */}
        <circle
          cx={todayX.toFixed(1)}
          cy={todayY.toFixed(1)}
          r="3"
          fill={dotColor}
        />
      </svg>

      {/* Chicago avg annotation */}
      <div className="sparkline-avg-note">
        <span className="sparkline-avg-dash" aria-hidden="true" />
        Chicago avg: 35
      </div>
    </div>
  );
}

export function getConfidenceReasons(result: ScoreResponse): string[] {
  return inferConfidenceReasons(result);
}

export function getMeaningInsights(result: ScoreResponse): string[] {
  return inferMeaning(result);
}

// ---------------------------------------------------------------------------
// NeighborhoodContextCard
// Shows (1) address vs neighborhood median score bars, (2) score-history
// sparkline, (3) a generated "how this compares" blurb.
// Slug detection is client-side via NEIGHBORHOOD_BBOXES; data comes from the
// existing /neighborhood/{slug} endpoint which now returns median_score.
// ---------------------------------------------------------------------------

function scoreBarColor(score: number): string {
  if (score <= 30) return "#22c55e";
  if (score <= 60) return "#f59e0b";
  return "#ef4444";
}

function generateComparisonBlurb(
  addressScore: number,
  slugInfo: NeighborhoodSlugInfo,
  medianScore: number | null | undefined,
): string {
  const areaStr = slugInfo.exact ? slugInfo.name : `near ${slugInfo.name}`;

  if (medianScore == null) {
    if (addressScore > 50) return `At ${addressScore}, this address scores above Chicago's typical range of 20–40. Disruption signals are elevated versus most of the city.`;
    if (addressScore > 40) return `At ${addressScore}, this address is modestly above Chicago's typical range of 20–40.`;
    if (addressScore < 20) return `At ${addressScore}, this address is below Chicago's typical range — a positive signal for near-term access.`;
    return `At ${addressScore}, this address falls within Chicago's typical disruption range of 20–40.`;
  }

  const diff = addressScore - medianScore;

  if (diff > 20) {
    return `This address scores ${diff} points above the ${areaStr} median of ${medianScore}, pointing to localized disruption well above the neighborhood baseline.`;
  }
  if (diff > 8) {
    return `Sitting above the ${areaStr} median of ${medianScore}, this address has somewhat elevated disruption compared to the surrounding area.`;
  }
  if (diff < -20) {
    return `At ${Math.abs(diff)} points below the ${areaStr} median of ${medianScore}, this address is in noticeably better shape than most of the neighborhood.`;
  }
  if (diff < -8) {
    return `This address scores below the ${areaStr} typical level of ${medianScore} — a positive signal against the local area baseline.`;
  }
  return `Broadly in line with the ${areaStr} median of ${medianScore}. The score reflects neighborhood-wide conditions rather than a site-specific spike.`;
}

type ScoreBarRowProps = {
  label: string;
  score?: number;
  color?: string;
  // For the "Chicago typical" row we show a range band instead of a single bar
  rangeMin?: number;
  rangeMax?: number;
  dimLabel?: boolean;
};

function ScoreBarRow({ label, score, color, rangeMin, rangeMax, dimLabel }: ScoreBarRowProps) {
  const LABEL_W = 148;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "10px", height: "32px" }}>
      {/* Label */}
      <div style={{
        width: `${LABEL_W}px`, flexShrink: 0, textAlign: "right",
        fontSize: "0.72rem", fontWeight: 600,
        color: dimLabel ? "var(--text-muted, #64748b)" : "var(--text-soft, #94a3b8)",
        paddingRight: "2px",
      }}>
        {label}
      </div>

      {/* Track */}
      <div style={{
        flex: 1, height: "10px", position: "relative",
        background: "rgba(255,255,255,0.06)", borderRadius: "5px", overflow: "hidden",
      }}>
        {/* Range band (Chicago typical) */}
        {rangeMin != null && rangeMax != null && (
          <div style={{
            position: "absolute", top: 0, bottom: 0,
            left: `${rangeMin}%`, width: `${rangeMax - rangeMin}%`,
            background: "rgba(148,163,184,0.28)", borderRadius: "2px",
          }} />
        )}
        {/* Single-value bar */}
        {score != null && color && (
          <div style={{
            position: "absolute", top: 0, bottom: 0, left: 0,
            width: `${score}%`, background: color,
            borderRadius: "5px", transition: "width 0.55s ease-out",
          }} />
        )}
      </div>

      {/* Value label */}
      <div style={{
        width: "32px", flexShrink: 0, textAlign: "right",
        fontSize: "0.72rem", fontWeight: 700,
        color: dimLabel ? "var(--text-muted, #64748b)" : "var(--text-soft, #94a3b8)",
      }}>
        {score != null ? score : rangeMin != null ? `${rangeMin}–${rangeMax}` : ""}
      </div>
    </div>
  );
}

// ─── Area trend sparkline (data-062) ──────────────────────────────────────────
// Renders a simple SVG line chart of daily avg disruption over 30 days.
// Visually mirrors ScoreSparkline but uses TrendDay[] from /score-trend.

function AreaTrendSparkline({ trend }: { trend: TrendDay[] }) {
  if (trend.length < 2) return null;

  const W = 200; const H = 44; const PX = 6; const PY = 5;
  const innerW = W - PX * 2;
  const innerH = H - PY * 2;

  const scores = trend.map((d) => d.avg_disruption);
  const minVal = Math.max(0,   Math.min(...scores) - 6);
  const maxVal = Math.min(100, Math.max(...scores) + 6);
  const range  = maxVal - minVal || 1;

  const toX = (i: number) => PX + (i / (scores.length - 1)) * innerW;
  const toY = (v: number) => PY + (1 - (v - minVal) / range) * innerH;

  const linePath = scores
    .map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
    .join(" ");
  const areaPath = linePath
    + ` L${toX(scores.length - 1).toFixed(1)},${H} L${PX},${H} Z`;

  const first = scores[0];
  const last  = scores[scores.length - 1];
  const delta = last - first;
  // Improving = falling disruption = green; worsening = rising = red
  const trendColor = delta <= -3 ? "#4ade80" : delta >= 3 ? "#f87171" : "#94a3b8";
  const trendLabel = delta <= -3 ? `▼ ${Math.abs(delta)} pts` : delta >= 3 ? `▲ ${delta} pts` : "Stable";

  const gradId = `area-trend-fill-${Math.random().toString(36).slice(2, 7)}`;

  return (
    <div className="sparkline-wrapper">
      <div className="sparkline-header">
        <span className="sparkline-label">{trend.length} days · {trend[trend.length - 1].sample_count} searches</span>
        <span className="sparkline-trend" style={{ color: trendColor }}>{trendLabel}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sparkline-svg" aria-hidden="true">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#60a5fa" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke="#60a5fa" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={toX(scores.length - 1)} cy={toY(last)} r="2.5" fill="#60a5fa" />
      </svg>
    </div>
  );
}

type NeighborhoodContextCardProps = {
  result: ScoreResponse;
  scoreHistory: ScoreHistoryEntry[];
  scoreTrend?: TrendDay[];
  lat?: number | null;
  lon?: number | null;
};

export function NeighborhoodContextCard({ result, scoreHistory, scoreTrend = [], lat, lon }: NeighborhoodContextCardProps) {
  const [hood, setHood] = useState<NeighborhoodResponse | null>(null);
  const [hoodLoading, setHoodLoading] = useState(false);

  const slugInfo = useMemo<NeighborhoodSlugInfo | null>(
    () => (lat != null && lon != null ? detectNeighborhoodSlug(lat, lon) : null),
    [lat, lon],
  );

  useEffect(() => {
    if (!slugInfo) { setHood(null); return; }
    setHoodLoading(true);
    fetchNeighborhood(slugInfo.slug).then((data) => {
      setHood(data);
      setHoodLoading(false);
    });
  }, [slugInfo?.slug]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasHistory  = scoreHistory.length >= 2;
  const hasTrend    = scoreTrend.length >= 2;

  // Don't render when we have nothing to show.
  if (!hasHistory && !hasTrend && !lat && !lon) return null;

  const score          = result.disruption_score;
  const medianScore    = hood?.median_score ?? null;
  const neighborhoodName = hood?.name ?? slugInfo?.name ?? null;
  const blurb          = slugInfo
    ? generateComparisonBlurb(score, slugInfo, medianScore)
    : null;

  return (
    <div>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "8px", marginBottom: "18px", flexWrap: "wrap" }}>
        <div>
          <p style={{
            fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em",
            textTransform: "uppercase", color: "var(--text-muted, #64748b)", marginBottom: "3px",
          }}>
            Neighborhood context
          </p>
          <p style={{ fontSize: "0.82rem", color: "var(--text-soft, #94a3b8)", margin: 0 }}>
            {hoodLoading
              ? "Locating neighborhood…"
              : neighborhoodName
              ? slugInfo?.exact
                ? `${neighborhoodName} · ${result.address}`
                : `Near ${neighborhoodName}`
              : "Chicago context"}
          </p>
        </div>
        {slugInfo && hood && (
          <a
            href={`/neighborhood/${slugInfo.slug}`}
            style={{ fontSize: "0.71rem", color: "#60a5fa", textDecoration: "none", fontWeight: 500, whiteSpace: "nowrap" }}
          >
            View {hood.name} →
          </a>
        )}
      </div>

      {/* ── Score bar comparison ─────────────────────────────────────── */}
      <div style={{ marginBottom: "18px" }}>
        <ScoreBarRow
          label="This address"
          score={score}
          color={scoreBarColor(score)}
        />
        {(medianScore != null || hoodLoading) && (
          <ScoreBarRow
            label={neighborhoodName ? `${neighborhoodName} median` : "Neighborhood median"}
            score={hoodLoading ? undefined : (medianScore ?? undefined)}
            color={hoodLoading ? undefined : "#60a5fa"}
            dimLabel
          />
        )}
        <ScoreBarRow
          label="Chicago typical"
          rangeMin={20}
          rangeMax={40}
          dimLabel
        />
      </div>

      {/* ── Per-address sparkline ────────────────────────────────────── */}
      {hasHistory && (
        <div style={{
          marginBottom: "16px", paddingTop: "14px",
          borderTop: "1px solid rgba(255,255,255,0.055)",
        }}>
          <p style={{
            fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em",
            textTransform: "uppercase", color: "var(--text-muted, #64748b)", marginBottom: "8px",
          }}>
            Score trend
          </p>
          <ScoreSparkline history={scoreHistory} currentScore={score} />
        </div>
      )}

      {/* ── Area trend sparkline (data-062) ──────────────────────────── */}
      {hasTrend && (
        <div style={{
          marginBottom: "16px", paddingTop: "14px",
          borderTop: "1px solid rgba(255,255,255,0.055)",
        }}>
          <p style={{
            fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em",
            textTransform: "uppercase", color: "var(--text-muted, #64748b)", marginBottom: "2px",
          }}>
            Area · 30-day trend
          </p>
          <p style={{ fontSize: "0.68rem", color: "var(--text-muted, #64748b)", margin: "0 0 8px" }}>
            Avg disruption score within 1 km
          </p>
          <AreaTrendSparkline trend={scoreTrend} />
        </div>
      )}

      {/* ── Comparison blurb ─────────────────────────────────────────── */}
      {(blurb || (!slugInfo && lat != null)) && (
        <div style={{
          paddingTop: hasHistory ? "14px" : 0,
          borderTop: hasHistory ? "1px solid rgba(255,255,255,0.055)" : "none",
        }}>
          <p style={{
            fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em",
            textTransform: "uppercase", color: "var(--text-muted, #64748b)", marginBottom: "6px",
          }}>
            How this compares
          </p>
          <p style={{ fontSize: "0.82rem", color: "var(--text-soft, #94a3b8)", lineHeight: 1.65, margin: 0 }}>
            {blurb ?? generateComparisonBlurb(score, { slug: "", name: "Chicago", exact: true }, null)}
          </p>
          {hood?.sample_size === 0 && (
            <p style={{ fontSize: "0.67rem", color: "var(--text-muted, #64748b)", margin: "6px 0 0", fontStyle: "italic" }}>
              Neighborhood median is a calibrated estimate; live history data will replace this when the database is connected.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignalTimeline  (app-task)
// Horizontal Gantt-style timeline: one bar per top_risk_detail, colored by
// impact type, spanning start_date → end_date. Click a bar to expand the
// existing PermitDetailPanel. Today is marked with a vertical rule.
// ---------------------------------------------------------------------------

// Semantic color palette — 5 categories matching the legend spec.
const TL_COLOR: Record<string, string> = {
  closure_full:        "#EF4444",   // red   — traffic / access
  closure_multi_lane:  "#EF4444",
  closure_single_lane: "#EF4444",
  demolition:          "#10B981",   // teal  — construction family
  construction:        "#10B981",
  light_permit:        "#F59E0B",   // amber — noise / minor
  utility:             "#8B5CF6",   // purple — utility
};
const TL_COLOR_DEFAULT = "#6B7280"; // gray — other

// Maps impact_type → legend category key
const TL_CATEGORY: Record<string, string> = {
  closure_full:        "traffic",
  closure_multi_lane:  "traffic",
  closure_single_lane: "traffic",
  demolition:          "construction",
  construction:        "construction",
  light_permit:        "noise",
  utility:             "utility",
};

const TL_TYPE_LABEL: Record<string, string> = {
  closure_full:        "Full closure",
  closure_multi_lane:  "Multi-lane closure",
  closure_single_lane: "Lane closure",
  demolition:          "Demolition",
  construction:        "Construction",
  light_permit:        "Permitted work",
  utility:             "Utility work",
};

const TL_LEGEND = [
  { key: "traffic",      color: "#EF4444", label: "Traffic / Access disruption" },
  { key: "construction", color: "#10B981", label: "Construction"                },
  { key: "noise",        color: "#F59E0B", label: "Noise"                       },
  { key: "utility",      color: "#8B5CF6", label: "Utility"                     },
  { key: "other",        color: "#6B7280", label: "Other"                       },
] as const;

const MONTH_SHORT_TL = [
  "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec",
] as const;

type TLRow = {
  id: string;
  detail: TopRiskDetail;
  typeLabel: string;
  color: string;
  category: string;
  startPct: number;
  endPct: number;
  openStart: boolean;
  openEnd: boolean;
  daysLeft: number | null;   // null = open-ended, negative = already ended
  startLabel: string;
  endLabel: string;
};

type TLData = {
  rows: TLRow[];
  todayPct: number;
  ticks: { label: string; pct: number }[];
};

function buildTLData(details: TopRiskDetail[]): TLData | null {
  const dated = details.filter((d) => d.start_date || d.end_date);
  if (!dated.length) return null;

  const parseIso = (iso: string) => new Date(iso + "T00:00:00Z");

  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);

  // Initial window: 14 days back → 60 days forward
  let winStart = new Date(today); winStart.setUTCDate(winStart.getUTCDate() - 14);
  let winEnd   = new Date(today); winEnd.setUTCDate(winEnd.getUTCDate() + 60);

  // Expand to fit all signal dates
  for (const d of dated) {
    if (d.start_date) { const sd = parseIso(d.start_date); if (sd < winStart) winStart = sd; }
    if (d.end_date)   { const ed = parseIso(d.end_date);   if (ed > winEnd)   winEnd   = ed; }
  }

  // 4-day padding on each side
  winStart = new Date(winStart); winStart.setUTCDate(winStart.getUTCDate() - 4);
  winEnd   = new Date(winEnd);   winEnd.setUTCDate(winEnd.getUTCDate() + 4);

  const span  = winEnd.getTime() - winStart.getTime();
  const toPct = (d: Date) =>
    Math.max(0, Math.min(100, ((d.getTime() - winStart.getTime()) / span) * 100));

  const todayPct = toPct(today);

  // Month-boundary tick marks
  const ticks: TLData["ticks"] = [];
  let tick = new Date(Date.UTC(winStart.getUTCFullYear(), winStart.getUTCMonth() + 1, 1));
  while (tick.getTime() <= winEnd.getTime()) {
    ticks.push({
      label: `${MONTH_SHORT_TL[tick.getUTCMonth()]} ${tick.getUTCFullYear()}`,
      pct: toPct(tick),
    });
    tick = new Date(Date.UTC(tick.getUTCFullYear(), tick.getUTCMonth() + 1, 1));
  }

  const fmtDate = (iso: string | null): string => {
    if (!iso) return "Open";
    const d = new Date(iso + "T00:00:00Z");
    return `${MONTH_SHORT_TL[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
  };

  const rows: TLRow[] = dated.map((d, i) => {
    const sDate = d.start_date ? parseIso(d.start_date) : winStart;
    const eDate = d.end_date   ? parseIso(d.end_date)   : winEnd;
    const daysLeft = d.end_date
      ? Math.ceil((parseIso(d.end_date).getTime() - today.getTime()) / 86_400_000)
      : null;
    return {
      id:         `tl-${d.project_id}-${i}`,
      detail:     d,
      typeLabel:  TL_TYPE_LABEL[d.impact_type] ?? d.impact_type,
      color:      TL_COLOR[d.impact_type] ?? TL_COLOR_DEFAULT,
      category:   TL_CATEGORY[d.impact_type] ?? "other",
      startPct:   toPct(sDate),
      endPct:     toPct(eDate),
      openStart:  !d.start_date,
      openEnd:    !d.end_date,
      daysLeft,
      startLabel: fmtDate(d.start_date),
      endLabel:   fmtDate(d.end_date),
    };
  });

  return { rows, todayPct, ticks };
}

type SignalTimelineProps = { details: TopRiskDetail[] };

export function SignalTimeline({ details }: SignalTimelineProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId]   = useState<string | null>(null);

  const data = useMemo(() => buildTLData(details), [details]);

  if (!data) return null;

  const { rows, todayPct, ticks } = data;
  const expandedRow = rows.find((r) => r.id === expandedId) ?? null;
  const hoveredRow  = rows.find((r) => r.id === hoveredId)  ?? null;
  const LABEL_W = 162; // px — label column width

  function toggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  // Only show legend categories that actually appear in this result set.
  const presentCategories = new Set(rows.map((r) => r.category));
  const visibleLegend = TL_LEGEND.filter((l) => presentCategories.has(l.key));

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: "14px" }}>
        <p style={{
          fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em",
          textTransform: "uppercase", color: "var(--text-muted, #64748b)", marginBottom: "4px",
        }}>
          Active window timeline
        </p>
        <p style={{ fontSize: "0.78rem", color: "var(--text-soft, #94a3b8)", margin: 0 }}>
          Each bar spans a signal&rsquo;s active date range. Hover for details — click to expand permit info.
        </p>
      </div>

      {/* ── Hover info panel ────────────────────────────────────────── */}
      <div style={{
        minHeight: "52px",
        marginBottom: "10px",
        padding: hoveredRow ? "10px 14px" : "0",
        borderRadius: "8px",
        background: hoveredRow ? "rgba(255,255,255,0.04)" : "transparent",
        border: hoveredRow ? "1px solid rgba(255,255,255,0.07)" : "1px solid transparent",
        transition: "background 0.1s, border-color 0.1s",
      }}>
        {hoveredRow ? (
          <div style={{ display: "flex", gap: "24px", flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "7px" }}>
              <span style={{
                width: "10px", height: "10px", borderRadius: "2px",
                background: hoveredRow.color, flexShrink: 0,
              }} />
              <strong style={{ fontSize: "0.78rem", color: "var(--text-soft, #94a3b8)" }}>
                {/* data-043: prefer Claude display_title over raw title */}
                {hoveredRow.detail.display_title ?? hoveredRow.detail.title ?? hoveredRow.typeLabel}
              </strong>
            </span>
            {hoveredRow.detail.description && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #64748b)" }}>
                {hoveredRow.detail.description}
              </span>
            )}
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted, #64748b)" }}>
              {hoveredRow.startLabel} – {hoveredRow.endLabel}
            </span>
            {/* data-043: show pre-formatted distance when available, else compute */}
            {(hoveredRow.detail.distance ?? (hoveredRow.detail.distance_m > 0 ? null : null)) && (
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted, #64748b)" }}>
                {hoveredRow.detail.distance}
              </span>
            )}
            {!hoveredRow.detail.distance && hoveredRow.detail.distance_m > 0 && (
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted, #64748b)" }}>
                {Math.round(hoveredRow.detail.distance_m * 3.28084).toLocaleString()} ft away
              </span>
            )}
          </div>
        ) : (
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted, #64748b)", margin: 0, opacity: 0.5 }}>
            Hover a bar to see signal details
          </p>
        )}
      </div>

      {/* Scrollable timeline */}
      <div style={{ overflowX: "auto" }}>
        <div style={{ minWidth: "440px" }}>

          {/* ── Month axis ───────────────────────────────────────────── */}
          <div style={{ display: "flex", marginBottom: "4px" }}>
            <div style={{ width: `${LABEL_W}px`, flexShrink: 0 }} />
            <div style={{ flex: 1, position: "relative", height: "22px" }}>
              {ticks.map((t) => (
                <span
                  key={t.label}
                  style={{
                    position: "absolute", left: `${t.pct}%`,
                    transform: "translateX(-50%)",
                    fontSize: "0.65rem", fontWeight: 500,
                    color: "var(--text-muted, #64748b)", whiteSpace: "nowrap",
                  }}
                >
                  {t.label}
                </span>
              ))}
              {/* Today label */}
              <span style={{
                position: "absolute", left: `${todayPct}%`,
                transform: "translateX(-50%)",
                fontSize: "0.6rem", fontWeight: 700,
                color: "#60a5fa", textTransform: "uppercase",
                letterSpacing: "0.07em", whiteSpace: "nowrap",
              }}>
                Today
              </span>
            </div>
          </div>

          {/* ── Row body ──────────────────────────────────────────────── */}
          <div style={{ position: "relative" }}>

            {/* Today vertical rule */}
            <div
              aria-hidden="true"
              style={{
                position: "absolute", top: 0, bottom: 0,
                left: `calc(${LABEL_W}px + ${todayPct / 100} * (100% - ${LABEL_W}px))`,
                width: "1.5px",
                background: "rgba(96,165,250,0.28)",
                zIndex: 0, pointerEvents: "none",
              }}
            />

            {rows.map((row, index) => {
              const daysLabel = row.daysLeft === null
                ? "open"
                : row.daysLeft < 0
                ? "ended"
                : `${row.daysLeft}d`;
              const barWidthPct = Math.max(row.endPct - row.startPct, 1.8);

              return (
                <div
                  key={row.id}
                  style={{
                    display: "flex", alignItems: "center", height: "48px",
                    borderBottom: index < rows.length - 1
                      ? "1px solid rgba(255,255,255,0.045)" : "none",
                  }}
                >
                  {/* Label column */}
                  <div style={{
                    width: `${LABEL_W}px`, flexShrink: 0,
                    paddingRight: "14px", textAlign: "right",
                  }}>
                    <div style={{
                      fontSize: "0.72rem", fontWeight: 600, lineHeight: 1.3,
                      color: "var(--text-soft, #94a3b8)",
                    }}>
                      {row.typeLabel}
                    </div>
                    {/* data-043: prefer display_title over raw title in Gantt row label */}
                    {(row.detail.display_title ?? row.detail.title) && (
                      <div style={{
                        fontSize: "0.6rem", color: "var(--text-muted, #64748b)",
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap", maxWidth: `${LABEL_W - 14}px`,
                        marginLeft: "auto",
                      }}>
                        {row.detail.display_title ?? row.detail.title}
                      </div>
                    )}
                  </div>

                  {/* Track column */}
                  <div style={{ flex: 1, position: "relative", height: "100%" }}>
                    {/* Centre-line guide */}
                    <div aria-hidden="true" style={{
                      position: "absolute", top: "50%", left: 0, right: 0,
                      transform: "translateY(-50%)",
                      height: "1px", background: "rgba(255,255,255,0.05)",
                    }} />

                    {/* Colored bar */}
                    <button
                      type="button"
                      aria-pressed={expandedId === row.id}
                      aria-label={`${row.typeLabel}${row.detail.title ? ": " + row.detail.title : ""}. ${row.startLabel} to ${row.endLabel}. Click for permit details.`}
                      onClick={() => toggle(row.id)}
                      onMouseEnter={(e) => {
                        setHoveredId(row.id);
                        e.currentTarget.style.opacity = "1";
                      }}
                      onMouseLeave={(e) => {
                        setHoveredId(null);
                        e.currentTarget.style.opacity = expandedId === row.id ? "1" : "0.76";
                      }}
                      style={{
                        position: "absolute",
                        top: "50%", transform: "translateY(-50%)",
                        left: `${row.startPct}%`,
                        width: `${barWidthPct}%`,
                        height: "20px",
                        borderRadius: `${row.openStart ? 3 : 5}px ${row.openEnd ? 3 : 5}px ${row.openEnd ? 3 : 5}px ${row.openStart ? 3 : 5}px`,
                        background: row.color,
                        opacity: expandedId === row.id ? 1 : 0.76,
                        cursor: "pointer",
                        border: expandedId === row.id
                          ? "2px solid rgba(255,255,255,0.55)"
                          : row.openStart || row.openEnd
                          ? `1px dashed ${row.color}`
                          : "none",
                        outline: "none",
                        boxShadow: expandedId === row.id
                          ? `0 0 0 3px ${row.color}44`
                          : "none",
                        transition: "opacity 0.12s, box-shadow 0.12s",
                        zIndex: 1,
                        // Room for the days label on the right edge
                        paddingRight: "4px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "flex-end",
                        overflow: "hidden",
                      }}
                    >
                      {/* Days remaining — right edge of bar */}
                      <span style={{
                        fontSize: "0.58rem", fontWeight: 700, lineHeight: 1,
                        color: "rgba(255,255,255,0.82)",
                        whiteSpace: "nowrap",
                        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
                        pointerEvents: "none",
                      }}>
                        {daysLabel}
                      </span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Legend ──────────────────────────────────────────────── */}
          {visibleLegend.length > 0 && (
            <div style={{
              display: "flex", gap: "16px", flexWrap: "wrap",
              marginTop: "14px", paddingTop: "12px",
              borderTop: "1px solid rgba(255,255,255,0.06)",
              alignItems: "center",
            }}>
              {visibleLegend.map((l) => (
                <span key={l.key} style={{
                  display: "flex", alignItems: "center", gap: "6px",
                  fontSize: "0.67rem", color: "var(--text-muted, #64748b)",
                }}>
                  <span style={{
                    width: "10px", height: "10px", borderRadius: "2px",
                    background: l.color, flexShrink: 0,
                  }} />
                  {l.label}
                </span>
              ))}
              <span style={{
                fontSize: "0.67rem", color: "var(--text-muted, #64748b)",
                marginLeft: "auto", fontStyle: "italic",
              }}>
                Dashed edge = open-ended date
              </span>
            </div>
          )}
        </div>
      </div>

      {/* ── Expanded permit detail panel ──────────────────────────── */}
      {expandedRow && (
        <div style={{ marginTop: "14px" }}>
          <PermitDetailPanel
            detail={expandedRow.detail}
            onClose={() => setExpandedId(null)}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WatchlistForm — "Monitor this address"
// Shown inline when disruption_score > 50. Captures email + threshold and
// POSTs to /watch. Works on the free tier (always shows confirmation);
// actual alert email delivery is gated behind Pro.
// ---------------------------------------------------------------------------

// "Drop below" thresholds — alert fires when score clears below the value.
const WATCH_THRESHOLDS = [
  { value: 40 as const, label: "40", desc: "noticeable improvement" },
  { value: 30 as const, label: "30", desc: "significant clearance"  },
  { value: 20 as const, label: "20", desc: "near-normal conditions" },
];
type ThresholdVal = 40 | 30 | 20;

function pickDefaultThreshold(_score: number): ThresholdVal {
  // 40 is the most useful default — catches meaningful clearance without
  // waiting for near-zero conditions.
  return 40;
}

type WatchFormState = "idle" | "submitting" | "confirmed" | "error";

type WatchlistFormProps = {
  address: string;
  score: number;
};

export function WatchlistForm({ address, score }: WatchlistFormProps) {
  const [email, setEmail]         = useState("");
  const [threshold, setThreshold] = useState<ThresholdVal>(pickDefaultThreshold(score));
  const [formState, setFormState] = useState<WatchFormState>("idle");
  const [confirmed, setConfirmed] = useState<WatchResponse | null>(null);
  const [errorMsg, setErrorMsg]   = useState<string | null>(null);

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const selectedOpt = WATCH_THRESHOLDS.find((t) => t.value === threshold)!;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!emailValid || formState === "submitting") return;
    setFormState("submitting");
    setErrorMsg(null);
    try {
      const res = await subscribeWatch({ email, address, threshold });
      setConfirmed(res);
      setFormState("confirmed");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Could not set up the alert. Try again.",
      );
      setFormState("error");
    }
  }

  // ── Confirmed state ─────────────────────────────────────────────────────
  if (formState === "confirmed" && confirmed) {
    return (
      <div className="watch-confirmed-card detail-card" style={{ padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <span style={{ fontSize: "1.15rem", color: "#22c55e", lineHeight: 1 }}>✓</span>
          <p style={{ margin: 0, fontWeight: 700, fontSize: "0.95rem", color: "var(--text)" }}>
            You&rsquo;ll get an email when disruption clears.
          </p>
        </div>
        <p style={{ margin: "0 0 14px", fontSize: "0.82rem", color: "var(--text-soft)" }}>
          Alert fires when the score for <strong>{confirmed.address}</strong> drops below{" "}
          <strong>{confirmed.threshold}</strong>. Watching <strong>{confirmed.email}</strong>.
        </p>

        <div className="watch-pro-note">
          <span className="watch-pro-badge">Pro</span>
          <span>
            Email delivery is available on the Pro plan.{" "}
            Your address is saved — <a href="#pricing-section" style={{ color: "#a78bfa", textDecoration: "underline", textUnderlineOffset: "2px" }}>upgrade to activate</a>.
          </span>
        </div>

        {confirmed.demo && (
          <p style={{ margin: "10px 0 0", fontSize: "0.67rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            Live database not yet connected. Your alert will be queued when the backend goes live.
          </p>
        )}
      </div>
    );
  }

  // ── Idle / submitting / error state ──────────────────────────────────────
  return (
    <div className="watch-card detail-card" style={{ padding: "20px 24px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
        <div>
          <p style={{ fontSize: "0.67rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#f59e0b", marginBottom: "3px" }}>
            Monitor this address
          </p>
          <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-soft)" }}>
            Score is currently <strong>{score}</strong>. Get notified when disruption clears.
          </p>
        </div>
        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", whiteSpace: "nowrap", paddingTop: "4px" }}>
          Free to set up &middot; Pro for email delivery
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        {/* Threshold selector */}
        <div style={{ marginBottom: "14px" }}>
          <p style={{ fontSize: "0.7rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Alert me when score drops below
          </p>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
            {WATCH_THRESHOLDS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`watch-threshold-btn${threshold === opt.value ? " watch-threshold-btn--active" : ""}`}
                onClick={() => setThreshold(opt.value)}
                aria-pressed={threshold === opt.value}
              >
                {opt.label}
              </button>
            ))}
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontStyle: "italic" }}>
              Current score: {score}
            </span>
          </div>
          <p style={{ margin: "6px 0 0", fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Alert fires on {selectedOpt.desc} — when score drops below {selectedOpt.label}.
          </p>
        </div>

        {/* Email + submit */}
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <input
            type="email"
            className="watch-email-input"
            placeholder="your@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-label="Email address for alerts"
            required
            autoComplete="email"
          />
          <button
            type="submit"
            className="watch-submit-btn"
            disabled={!emailValid || formState === "submitting"}
          >
            {formState === "submitting" ? "Setting up…" : "Set alert"}
          </button>
        </div>

        {/* Error */}
        {formState === "error" && errorMsg && (
          <p style={{ margin: "8px 0 0", fontSize: "0.78rem", color: "#f87171" }}>
            {errorMsg}
          </p>
        )}
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CommuteChecker
// Collapsible section below the main score. User inputs a second address
// (workplace/destination); the app queries /commute for the corridor score,
// badge (Low/Moderate/High), and any CTA service alerts in the corridor.
// ---------------------------------------------------------------------------

type CommuteCheckerProps = {
  homeAddress: string;
};

function _commuteBadgeColor(badge: string): string {
  if (badge === "Low") return "#10b981";
  if (badge === "Moderate") return "#f59e0b";
  return "#ef4444";
}

function _commuteSignalColor(impact_type: string | null): string {
  if (!impact_type) return "#6b7280";
  if (impact_type.startsWith("closure")) return "#ef4444";
  if (impact_type === "construction" || impact_type === "demolition") return "#10b981";
  return "#f59e0b";
}

export function CommuteChecker({ homeAddress }: CommuteCheckerProps) {
  const [isOpen, setIsOpen]       = useState(false);
  const [workAddr, setWorkAddr]   = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult]       = useState<CommuteResponse | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const suggestTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function handleCheck(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = workAddr.trim();
    if (!trimmed) return;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setShowSuggestions(false);
    try {
      const data = await fetchCommute(homeAddress, trimmed);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not score commute corridor. Try again.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleWorkAddrChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setWorkAddr(val);
    setResult(null);
    setError(null);
    if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current);
    if (val.trim().length >= 3) {
      suggestTimerRef.current = setTimeout(async () => {
        try {
          const hits = await fetchSuggestions(val);
          setSuggestions(hits);
          setShowSuggestions(hits.length > 0);
        } catch { /* ignore */ }
      }, 300);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }

  function pickSuggestion(s: string) {
    setWorkAddr(s);
    setSuggestions([]);
    setShowSuggestions(false);
  }

  const badgeColor = result ? _commuteBadgeColor(result.badge) : "#6b7280";

  return (
    <div className="commute-section">
      <button
        type="button"
        className={`commute-toggle${isOpen ? " commute-toggle--open" : ""}`}
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
      >
        <span className="commute-toggle-label">
          <span className="commute-toggle-icon" aria-hidden="true">🚇</span>
          Check my commute
        </span>
        <span className="commute-toggle-caret" aria-hidden="true">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="commute-panel">
          <p className="commute-description">
            Add a destination to score disruption along your commute corridor. The app queries all
            active signals between the two addresses and checks for CTA service alerts.
          </p>

          <form className="commute-form" onSubmit={handleCheck}>
            <div className="commute-addr-display">
              <span className="commute-addr-pin commute-addr-pin--home" aria-hidden="true">A</span>
              <span className="commute-addr-text">{homeAddress}</span>
            </div>
            <div className="commute-input-row">
              <span className="commute-addr-pin commute-addr-pin--work" aria-hidden="true">B</span>
              <div className="commute-input-shell">
                <input
                  id="commute-work"
                  className="commute-work-input"
                  type="text"
                  placeholder="Enter workplace or destination address"
                  value={workAddr}
                  onChange={handleWorkAddrChange}
                  onFocus={() => setShowSuggestions(suggestions.length > 0)}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                  autoComplete="off"
                  required
                />
                {showSuggestions && (
                  <ul className="commute-suggestions" role="listbox">
                    {suggestions.map((s) => (
                      <li
                        key={s}
                        role="option"
                        aria-selected={false}
                        className="commute-suggestion-item"
                        onMouseDown={() => pickSuggestion(s)}
                      >
                        {s}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                type="submit"
                className="commute-submit-btn"
                disabled={isLoading || !workAddr.trim()}
              >
                {isLoading ? "Scoring…" : "Score corridor"}
              </button>
            </div>
          </form>

          {error && <p className="commute-error">{error}</p>}

          {result && (
            <div className="commute-result">
              {/* Score + badge row */}
              <div className="commute-badge-row">
                <div className="commute-score-block">
                  <span className="commute-score-num" style={{ color: badgeColor }}>
                    {result.commute_score}
                  </span>
                  <span className="commute-score-label">corridor score</span>
                </div>
                <span
                  className="commute-badge"
                  style={{
                    background: `${badgeColor}1a`,
                    border: `1px solid ${badgeColor}40`,
                    color: badgeColor,
                  }}
                >
                  {result.badge} disruption
                </span>
                <span className="commute-signals-count">
                  {result.signals_count} active signal{result.signals_count !== 1 ? "s" : ""} in corridor
                </span>
              </div>

              {/* Corridor construction/closure signals */}
              {result.signals.length > 0 && (
                <div className="commute-signals-block">
                  <p className="commute-block-heading">Corridor signals</p>
                  <ul className="commute-signals-list">
                    {result.signals.slice(0, 6).map((sig: CommuteSignal, i: number) => (
                      <li key={i} className="commute-signal-item">
                        <span
                          className="commute-signal-dot"
                          style={{ background: _commuteSignalColor(sig.impact_type) }}
                          aria-hidden="true"
                        />
                        <span className="commute-signal-title">
                          {sig.title ?? sig.impact_type ?? "Unknown signal"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* CTA transit alerts */}
              {result.transit_alerts.length > 0 && (
                <div className="commute-signals-block">
                  <p className="commute-block-heading">CTA service alerts in corridor</p>
                  <ul className="commute-signals-list">
                    {result.transit_alerts.slice(0, 5).map((alert: CommuteSignal, i: number) => (
                      <li key={i} className="commute-signal-item commute-signal-item--transit">
                        <span className="commute-signal-dot commute-signal-dot--transit" aria-hidden="true" />
                        <span className="commute-signal-title">
                          {alert.title ?? "CTA service alert"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* CTA stations with no active alerts */}
              {result.transit_stations.length > 0 && result.transit_alerts.length === 0 && (
                <p className="commute-transit-clear">
                  {result.transit_stations.length} CTA station
                  {result.transit_stations.length !== 1 ? "s" : ""} in corridor — no active service alerts.
                </p>
              )}

              {result.mode === "demo" && (
                <p className="commute-demo-note">
                  Demo data — connect a live database for real corridor signals.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MobileScoreView
// Shown only on screens < 768px via CSS. Replaces the full results section
// with a three-zone layout optimised for "standing outside an apartment".
//  1. Giant score hero (top ~40% of viewport)
//  2. Three horizontally-scrolling signal pills
//  3. Share + Monitor CTAs, then "Switch to full report →"
// ---------------------------------------------------------------------------

type MobileScoreViewProps = {
  result: ScoreResponse;
  onShowFull: () => void;
};

function _mobileBand(score: number): { label: string; color: string } {
  if (score <= 24) return { label: "Low Risk",      color: "#10b981" };
  if (score <= 49) return { label: "Moderate Risk", color: "#f59e0b" };
  if (score <= 74) return { label: "High Risk",     color: "#ef4444" };
  return             { label: "Severe Risk",    color: "#7c3aed" };
}

function _pillLabel(impactType: string | null | undefined, title: string | null | undefined): string {
  if (title) return title.length > 38 ? title.slice(0, 35) + "…" : title;
  const MAP: Record<string, string> = {
    closure_full:         "Full Road Closure",
    closure_multi_lane:   "Multi-lane Closure",
    closure_single_lane:  "Lane Closure",
    construction:         "Construction",
    demolition:           "Demolition",
    light_permit:         "Street Permit",
    utility:              "Utility Work",
  };
  return MAP[impactType ?? ""] ?? "Active Signal";
}

function _pillColor(impactType: string | null | undefined): string {
  if (!impactType) return "#6b7280";
  if (impactType.startsWith("closure")) return "#ef4444";
  if (impactType === "construction" || impactType === "demolition") return "#10b981";
  if (impactType === "light_permit") return "#f59e0b";
  return "#8b5cf6";
}

export function MobileScoreView({ result, onShowFull }: MobileScoreViewProps) {
  const band = _mobileBand(result.disruption_score);

  // ── Share state ──────────────────────────────────────────────────────────
  const [shareState, setShareState] = useState<"idle" | "loading" | "copied" | "error">("idle");

  async function handleShare() {
    if (shareState === "loading") return;
    setShareState("loading");
    try {
      const saved = await saveReport(result);
      const url = `${window.location.origin}/report/${saved.report_id}`;
      if (typeof navigator.share === "function") {
        await navigator.share({
          title: `Disruption score — ${result.address}`,
          text: `${result.address} scores ${result.disruption_score}/100 (${band.label}) for near-term construction disruption.`,
          url,
        });
        setShareState("idle");
      } else {
        await navigator.clipboard.writeText(url);
        setShareState("copied");
        setTimeout(() => setShareState("idle"), 2500);
      }
    } catch {
      setShareState("error");
      setTimeout(() => setShareState("idle"), 2000);
    }
  }

  // ── Monitor (watchlist) state ────────────────────────────────────────────
  const [monitorOpen, setMonitorOpen]         = useState(false);
  const [monitorEmail, setMonitorEmail]       = useState("");
  const [monitorStatus, setMonitorStatus]     = useState<"idle" | "sending" | "done" | "error">("idle");

  const monitorEmailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(monitorEmail);

  async function handleMonitor(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!monitorEmailValid || monitorStatus === "sending") return;
    setMonitorStatus("sending");
    try {
      await subscribeWatch({ email: monitorEmail, address: result.address, threshold: 40 });
      setMonitorStatus("done");
    } catch {
      setMonitorStatus("error");
    }
  }

  // ── Signal pills (top 3) ─────────────────────────────────────────────────
  const pills = useMemo(() => {
    const details = result.top_risk_details ?? [];
    if (details.length > 0) {
      return details.slice(0, 3).map((d) => ({
        label: _pillLabel(d.impact_type, d.rewritten_title ?? d.title),
        color: _pillColor(d.impact_type),
        key: d.project_id,
      }));
    }
    return (result.top_risks ?? []).slice(0, 3).map((t, i) => ({
      label: _pillLabel(null, t),
      color: "#f59e0b",
      key: String(i),
    }));
  }, [result]);

  const extraCount = (result.top_risk_details?.length ?? result.top_risks?.length ?? 0) - 3;

  return (
    <div className="msv" aria-label="Mobile score summary">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="msv-hero" style={{ "--msv-band-color": band.color } as React.CSSProperties}>
        <p className="msv-eyebrow">Disruption Score</p>
        <div className="msv-score" style={{ color: band.color }}>
          {result.disruption_score}
        </div>
        <p className="msv-band" style={{ color: band.color }}>{band.label}</p>
        <p className="msv-address">{result.address}</p>
        {result.mode === "demo" && (
          <span className="msv-demo-badge">Demo data</span>
        )}
      </div>

      {/* ── Signal pills ──────────────────────────────────────────────────── */}
      {pills.length > 0 && (
        <div className="msv-pills-section">
          <p className="msv-pills-label">Active signals nearby</p>
          <div className="msv-pills-scroll" role="list">
            {pills.map((pill) => (
              <span
                key={pill.key}
                role="listitem"
                className="msv-pill"
                style={{
                  background: `${pill.color}18`,
                  border: `1px solid ${pill.color}45`,
                  color: pill.color,
                }}
              >
                <span
                  className="msv-pill-dot"
                  style={{ background: pill.color }}
                  aria-hidden="true"
                />
                {pill.label}
              </span>
            ))}
            {extraCount > 0 && (
              <button
                type="button"
                className="msv-pill msv-pill--more"
                onClick={onShowFull}
                style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8" }}
              >
                +{extraCount} more
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Actions ───────────────────────────────────────────────────────── */}
      <div className="msv-actions">
        {/* Share */}
        <button
          type="button"
          className="msv-action-btn msv-action-btn--share"
          onClick={handleShare}
          disabled={shareState === "loading"}
        >
          <span aria-hidden="true">{shareState === "copied" ? "✓" : shareState === "error" ? "✗" : "↗"}</span>
          {shareState === "loading" ? "Saving…"
            : shareState === "copied" ? "Link copied!"
            : shareState === "error"  ? "Share failed"
            : "Share this score"}
        </button>

        {/* Monitor */}
        {monitorStatus === "done" ? (
          <div className="msv-monitor-confirmed">
            <span aria-hidden="true">✓</span> Alert set — you&rsquo;ll hear when disruption clears.
          </div>
        ) : (
          <>
            <button
              type="button"
              className={`msv-action-btn msv-action-btn--monitor${monitorOpen ? " msv-action-btn--active" : ""}`}
              onClick={() => setMonitorOpen((v) => !v)}
            >
              <span aria-hidden="true">🔔</span>
              Monitor this address
            </button>
            {monitorOpen && (
              <form className="msv-monitor-form" onSubmit={handleMonitor}>
                <input
                  type="email"
                  className="msv-monitor-input"
                  placeholder="your@email.com"
                  value={monitorEmail}
                  onChange={(e) => setMonitorEmail(e.target.value)}
                  autoComplete="email"
                  required
                  aria-label="Email for disruption alerts"
                />
                <button
                  type="submit"
                  className="msv-monitor-submit"
                  disabled={!monitorEmailValid || monitorStatus === "sending"}
                >
                  {monitorStatus === "sending" ? "Setting up…" : "Alert me below 40"}
                </button>
                {monitorStatus === "error" && (
                  <p className="msv-monitor-error">Could not set alert. Try again.</p>
                )}
                <p className="msv-monitor-hint">
                  Fires when score drops below 40. Pro plan required for email delivery.
                </p>
              </form>
            )}
          </>
        )}
      </div>

      {/* ── Switch to full report ─────────────────────────────────────────── */}
      <div className="msv-full-link">
        <button type="button" className="msv-full-btn" onClick={onShowFull}>
          Switch to full report →
        </button>
      </div>
    </div>
  );
}
