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
  eyebrow: string;
  title: string;
  impact: "High" | "Medium" | "Low";
  rationale: string;
  evidence: string;
  chips: string[];
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
  const normalized = normalizeSentence(text);
  const simplified = normalized
    .replace(/^active\s+/i, "")
    .replace(/^a nearby\s+/i, "")
    .replace(/^nearby\s+/i, "")
    .replace(/^traffic and curb access are the dominant near-term disruption signals at this address$/i, "Traffic and curb access drive this score")
    .replace(/\bwithin roughly\b/gi, "~")
    .replace(/\bmeters\b/gi, "m")
    .replace(/\s+/g, " ");

  if (simplified.length <= 76) {
    return simplified;
  }

  const firstClause = simplified.split(/,| so | because /i)[0]?.trim();
  return firstClause && firstClause.length >= 20 ? firstClause : simplified;
}

function deriveDriverRationale(text: string): string {
  const normalized = text.toLowerCase();

  if (/closure|lane|traffic/.test(normalized)) {
    return "Direct roadway constraints are usually the fastest way nearby work changes day-to-day access.";
  }
  if (/through|window|days|months|timeline/.test(normalized)) {
    return "A defined active window makes the disruption easier to plan around and easier to trust.";
  }
  if (/within roughly|meters|adjacent|close proximity|within/.test(normalized)) {
    return "Proximity matters here: closer signals are more likely to be felt at the address itself.";
  }
  if (/permit|construction|site work|excavation|renovation/.test(normalized)) {
    return "Confirmed nearby work gives the score a concrete physical source rather than background neighborhood noise.";
  }
  if (/curb access|parking|loading|pickup|dropoff/.test(normalized)) {
    return "Curb friction often shows up before broader congestion and can change arrival quality quickly.";
  }

  return "This is one of the strongest plain-language signals returned by the scoring service.";
}

function extractRiskChips(text: string, impact: RiskCardModel["impact"]): string[] {
  const chips = new Set<string>([`${impact} impact`]);
  const normalized = text.toLowerCase();

  const meterMatch = text.match(/(\d{1,4})\s*meters?/i);
  if (meterMatch) {
    chips.add(`${meterMatch[1]} m away`);
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
    const impact = inferImpact(risk, index);
    return {
      id: `${risk}-${index}`,
      eyebrow: inferDriverEyebrow(risk),
      title: inferDriverTitle(risk),
      impact,
      rationale: deriveDriverRationale(risk),
      evidence: normalizeSentence(risk),
      chips: extractRiskChips(risk, impact),
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

export function ScoreHero({ result }: ScoreHeroProps) {
  const displayScore = useAnimatedScore(result.disruption_score);
  const scoreMessage = getScoreMessage(result.disruption_score);
  const timeline = useMemo(() => buildTimelineSummary(result), [result]);
  const modeLabel = result.mode === "demo" ? "Demo scenario" : "Live Chicago signal";

  return (
    <div className="score-hero">
      <div className="score-hero-copy">
        <p className="score-hero-kicker">Headline assessment</p>
        <div className="score-hero-topline">
          <p className="score-label">Disruption score</p>
          <p className="confidence-pill">{modeLabel}</p>
        </div>
        <div className="score-value score-value--animated">{displayScore}</div>
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
            <strong>{result.top_risks.length} surfaced</strong>
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
        <div className="confidence-summary-head">
          <p className="confidence-summary-label">Confidence</p>
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
      <p className="severity-footnote">Confidence speaks to evidence quality and specificity, not severity.</p>
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
            <div>
              <p className="risk-card-index">{risk.eyebrow}</p>
              <h3>{risk.title}</h3>
            </div>
            <span className={`impact-badge impact-badge--${risk.impact.toLowerCase()}`}>{risk.impact}</span>
          </div>
          <p className="risk-card-rationale">{risk.rationale}</p>
          <div className="risk-chip-row" aria-label="Driver metadata">
            {risk.chips.map((chip) => (
              <span key={chip} className="risk-chip">
                {chip}
              </span>
            ))}
          </div>
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

export function getConfidenceReasons(result: ScoreResponse): string[] {
  return inferConfidenceReasons(result);
}

export function getMeaningInsights(result: ScoreResponse): string[] {
  return inferMeaning(result);
}
