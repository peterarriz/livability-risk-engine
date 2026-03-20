"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { ScoreHistoryEntry, ScoreResponse, SeverityLevel, TopRiskDetail } from "@/lib/api";

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
  impact: "High" | "Medium" | "Low";
  rationale: string;
  evidence: string;
  chips: string[];
  rawText: string;        // humanized full signal text for expanded detail
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
    return {
      id: `${risk}-${index}`,
      eyebrow: inferDriverEyebrow(humanized),
      title: inferDriverTitle(humanized),
      impact,
      rationale: deriveDriverRationale(humanized),
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
  const displayScore = useAnimatedScore(result.disruption_score);
  const scoreMessage = getScoreMessage(result.disruption_score);
  const timeline = useMemo(() => buildTimelineSummary(result), [result]);
  const modeLabel = result.mode === "demo" ? "Demo scenario" : "Live Chicago signal";
  const gaugeBand = getGaugeBand(result.disruption_score);

  return (
    <div className="score-hero">
      <div className="score-hero-copy">
        <p className="score-hero-kicker">Headline assessment</p>
        <div className="score-hero-topline">
          <p className="score-label">Disruption score</p>
          <p className="confidence-pill">{modeLabel}</p>
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
        <p className="score-benchmark">{getBenchmarkText(result.disruption_score)}</p>

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
        </div>
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

  return (
    <div className="risk-card-section">
      <div className="risk-card-grid">
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
              <p className="risk-detail-text">{expandedCard.rawText}</p>
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
// ScoreSparkline  (data-025)
// Renders a compact SVG line chart of historical disruption scores.
// ---------------------------------------------------------------------------

type ScoreSparklineProps = {
  history: ScoreHistoryEntry[];
  currentScore: number;
};

export function ScoreSparkline({ history, currentScore }: ScoreSparklineProps) {
  // history is newest-first; reverse to render chronologically left→right.
  const points = useMemo(() => {
    const chronological = [...history].reverse();
    // Append the current live score as the rightmost point.
    const all = [...chronological, { disruption_score: currentScore, confidence: "LOW" as const, mode: "live" as const, created_at: null }];
    return all.map((e) => e.disruption_score);
  }, [history, currentScore]);

  if (points.length < 2) return null;

  const W = 160;
  const H = 36;
  const PAD = 2;
  const min = Math.max(0, Math.min(...points) - 5);
  const max = Math.min(100, Math.max(...points) + 5);
  const range = max - min || 1;

  function toX(i: number) {
    return PAD + (i / (points.length - 1)) * (W - PAD * 2);
  }
  function toY(v: number) {
    return PAD + (1 - (v - min) / range) * (H - PAD * 2);
  }

  const pathD = points.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const lastX = toX(points.length - 1);
  const lastY = toY(points[points.length - 1]);
  const trend = points.length >= 2 ? points[points.length - 1] - points[points.length - 2] : 0;
  const trendLabel = trend > 0 ? `↑ +${trend}` : trend < 0 ? `↓ ${trend}` : "→ stable";
  const trendColor = trend > 5 ? "#ef4444" : trend < -5 ? "#22c55e" : "#94a3b8";

  return (
    <div className="sparkline-wrapper" aria-label={`Score trend over ${points.length} readings`}>
      <div className="sparkline-meta">
        <span className="sparkline-label">{points.length} readings</span>
        <span className="sparkline-trend" style={{ color: trendColor }}>{trendLabel}</span>
      </div>
      <svg width={W} height={H} className="sparkline-svg" aria-hidden="true">
        <path d={pathD} fill="none" stroke="#64748b" strokeWidth="1.5" strokeLinejoin="round" />
        <circle cx={lastX} cy={lastY} r="3" fill={trendColor} />
      </svg>
    </div>
  );
}

export function getConfidenceReasons(result: ScoreResponse): string[] {
  return inferConfidenceReasons(result);
}

export function getMeaningInsights(result: ScoreResponse): string[] {
  return inferMeaning(result);
}
