"use client";

import { useEffect, useMemo, useState } from "react";

import type { ScoreResponse, SeverityLevel } from "@/lib/api";

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
  title: string;
  impact: "High" | "Medium" | "Low";
  rationale: string;
  evidence: string;
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
  { max: 24, label: "Low Disruption Risk", summary: "Mostly normal near-term livability conditions." },
  { max: 49, label: "Moderate Disruption Risk", summary: "Noticeable friction, but not a severe constraint." },
  { max: 74, label: "High Disruption Risk", summary: "Clear near-term disruption likely to affect daily experience." },
  { max: 100, label: "Severe Disruption Risk", summary: "Strong signals suggest meaningful near-term impact." },
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

function deriveDriverTitle(text: string): string {
  const normalized = normalizeSentence(text);

  if (/closure/i.test(normalized)) {
    return "Traffic impact from nearby closure";
  }
  if (/permit|construction|site work|excavation/i.test(normalized)) {
    return "Active nearby construction activity";
  }
  if (/through|window|days|months|timeline/i.test(normalized)) {
    return "Disruption window remains active";
  }
  if (/within roughly|meters|adjacent|close proximity/i.test(normalized)) {
    return "Close proximity to the address";
  }
  if (/curb access|parking|loading|pickup|dropoff/i.test(normalized)) {
    return "Access friction around the property";
  }

  return normalized;
}

function deriveDriverRationale(text: string): string {
  const normalized = normalizeSentence(text);

  if (/closure/i.test(normalized)) {
    return "Road or lane restrictions usually create the clearest short-term access friction.";
  }
  if (/through|window|days|months|timeline/i.test(normalized)) {
    return "A longer active window increases the chance the disruption affects planning decisions.";
  }
  if (/within roughly|meters|adjacent|close proximity/i.test(normalized)) {
    return "Signals close to the property are more likely to be felt directly at the address.";
  }
  if (/permit|construction|site work|excavation/i.test(normalized)) {
    return "Confirmed nearby work makes the score easier to trust than background neighborhood activity.";
  }

  return "This is one of the strongest plain-English signals returned by the scoring service.";
}

function buildRiskCards(result: ScoreResponse): RiskCardModel[] {
  return result.top_risks.map((risk, index) => ({
    id: `${risk}-${index}`,
    title: deriveDriverTitle(risk),
    impact: inferImpact(risk, index),
    rationale: deriveDriverRationale(risk),
    evidence: normalizeSentence(risk),
  }));
}

function inferConfidenceReasons(result: ScoreResponse): string[] {
  const reasons: string[] = [];
  const combinedText = [...result.top_risks, result.explanation].join(" ").toLowerCase();

  if (result.top_risks.length >= 3) {
    reasons.push("Multiple nearby signals detected");
  } else if (result.top_risks.length === 2) {
    reasons.push("More than one supporting signal is present");
  } else {
    reasons.push("The score is driven by a limited number of visible signals");
  }

  if (/through\s+\d{4}-\d{2}-\d{2}|next\s+\d+\s+days|active\s+closure\s+window|window/i.test(combinedText)) {
    reasons.push("An active construction or closure timeline is referenced");
  }

  if (/within roughly|meters|adjacent|address/i.test(combinedText)) {
    reasons.push("At least one signal is tied closely to the address");
  }

  if (result.confidence === "HIGH") {
    reasons.push("Evidence appears specific enough for a high-confidence read");
  } else if (result.confidence === "MEDIUM") {
    reasons.push("Evidence is useful, but not precise enough to treat as exact site conditions");
  } else {
    reasons.push("Available evidence should be treated as directional rather than definitive");
  }

  return reasons.slice(0, 3);
}

function inferMeaning(result: ScoreResponse): string[] {
  const insights: string[] = [];
  const combinedText = [...result.top_risks, result.explanation].join(" ").toLowerCase();

  if (result.severity.traffic === "HIGH" || /closure|traffic|curb access|parking|loading/i.test(combinedText)) {
    insights.push("Expect slower vehicle access, pickup friction, or reduced curb availability near peak hours.");
  }

  if (result.severity.noise !== "LOW" || /noise|construction|renovation|site work/i.test(combinedText)) {
    insights.push(
      result.severity.noise === "HIGH"
        ? "Sustained construction noise is likely to be noticeable during daytime work windows."
        : "Some daytime construction noise is possible, but it is not the dominant issue in this score."
    );
  }

  if (result.severity.dust === "HIGH" || /dust|excavation|demolition|vibration/i.test(combinedText)) {
    insights.push("Physical site activity may create dust or vibration sensitivity close to the property.");
  }

  if (insights.length === 0) {
    insights.push("Available city signals suggest limited day-to-day disruption, with normal access likely for most visits.");
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
      window: `Impact window: now through ${formatMonthYear(latest)}`,
      peak:
        diffDays <= 30
          ? "Peak disruption: immediate window"
          : diffDays <= 90
            ? "Peak disruption: next 30-90 days"
            : "Peak disruption: extended multi-month window",
      progress: Math.min(100, Math.max(18, 100 - diffDays / 2)),
    };
  }

  const horizonMatch = combinedText.match(/next\s+(\d{1,3})\s+days/i);
  if (horizonMatch) {
    const days = Number(horizonMatch[1]);
    return {
      label: `Now → next ${days} days`,
      window: `Impact window: active over the next ${days} days`,
      peak: days <= 90 ? "Peak disruption: next 30-90 days" : "Peak disruption: extended monitoring window",
      progress: Math.min(100, Math.max(24, days)),
    };
  }

  return {
    label: "Near-term activity window",
    window: "Impact window: timing is mentioned qualitatively in the score explanation",
    peak: "Peak disruption: monitor the strongest active driver",
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

export function ScoreHero({ result }: ScoreHeroProps) {
  const displayScore = useAnimatedScore(result.disruption_score);
  const scoreMessage = getScoreMessage(result.disruption_score);
  const timeline = useMemo(() => buildTimelineSummary(result), [result]);
  const modeLabel = result.mode === "demo" ? "Demo scenario" : "Live data • Chicago";

  return (
    <div className="score-hero">
      <div className="score-hero-copy">
        <p className="score-hero-kicker">Disruption analysis</p>
        <div className="score-hero-topline">
          <p className="score-label">Disruption score</p>
          <p className="confidence-pill">{modeLabel}</p>
        </div>
        <div className="score-value score-value--animated">{displayScore}</div>
        <h2 className="score-hero-title">{scoreMessage.label}</h2>
        <p className="score-hero-summary">{scoreMessage.summary}</p>
      </div>

      <div className="score-hero-sidecar">
        <p className="score-meta">Decision context for</p>
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
        </div>
      </div>
    </div>
  );
}

export function SeverityMeters({ severity, confidence, confidenceReasons }: SeverityMetersProps) {
  const rows = useMemo(
    () => [
      { label: "Noise", value: severity.noise, accent: "noise" },
      { label: "Traffic & curb access", value: severity.traffic, accent: "traffic" },
      { label: "Dust & vibration", value: severity.dust, accent: "dust" },
    ],
    [severity],
  );

  return (
    <div className="severity-stack">
      <div className="confidence-summary">
        <p className="confidence-summary-label">Confidence: {toTitleCase(confidence.toLowerCase())}</p>
        <p className="confidence-summary-copy">Based on:</p>
        <ul className="confidence-reason-list">
          {confidenceReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>

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
      <p className="severity-footnote">
        Confidence reflects evidence quality and specificity, not how severe the disruption feels.
      </p>
    </div>
  );
}

export function TopRiskGrid({ result }: TopRiskGridProps) {
  const riskCards = useMemo(() => buildRiskCards(result), [result]);

  return (
    <div className="risk-card-grid">
      {riskCards.map((risk, index) => (
        <article
          key={risk.id}
          className="risk-card card-entrance"
          style={{ animationDelay: `${index * 90}ms` }}
        >
          <div className="risk-card-head">
            <p className="risk-card-index">Driver {index + 1}</p>
            <span className={`impact-badge impact-badge--${risk.impact.toLowerCase()}`}>{risk.impact} impact</span>
          </div>
          <h3>{risk.title}</h3>
          <p className="risk-card-rationale">{risk.rationale}</p>
          <dl className="risk-card-meta">
            <div>
              <dt>Evidence</dt>
              <dd>{risk.evidence}</dd>
            </div>
          </dl>
        </article>
      ))}
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
          <p className="impact-window-kicker">Timeline view</p>
          <h3>Impact window</h3>
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

export function getConfidenceReasons(result: ScoreResponse): string[] {
  return inferConfidenceReasons(result);
}

export function getMeaningInsights(result: ScoreResponse): string[] {
  return inferMeaning(result);
}
