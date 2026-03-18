"use client";

import { useEffect, useMemo, useState } from "react";

import type { ScoreResponse, SeverityLevel } from "@/lib/api";

type ScoreHeroProps = {
  result: ScoreResponse;
};

type SeverityMetersProps = {
  severity: ScoreResponse["severity"];
};

type TopRiskGridProps = {
  result: ScoreResponse;
};

type ExplanationPanelProps = {
  explanation: string;
};

type RiskCardModel = {
  id: string;
  title: string;
  distance: string;
  timeline: string;
  confidence: ScoreResponse["confidence"];
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

function getScoreMessage(score: number) {
  return SCORE_COPY.find((entry) => score <= entry.max) ?? SCORE_COPY[SCORE_COPY.length - 1];
}

function extractDistance(text: string): string | null {
  const match = text.match(/within roughly ([^,]+?)(?:$|,)/i);
  return match ? `~${match[1].trim()}` : null;
}

function extractTimeline(text: string): string | null {
  const throughMatch = text.match(/through ([0-9]{4}-[0-9]{2}-[0-9]{2})/i);
  if (throughMatch) {
    return `Through ${throughMatch[1]}`;
  }

  const runsMatch = text.match(/active [^.]*/i);
  return runsMatch ? runsMatch[0] : null;
}

function buildRiskCards(result: ScoreResponse): RiskCardModel[] {
  const sharedDistance =
    result.top_risks.map((risk) => extractDistance(risk)).find(Boolean) ?? "Near address";
  const sharedTimeline =
    result.top_risks.map((risk) => extractTimeline(risk)).find(Boolean) ?? "Near-term window";

  return result.top_risks.map((risk, index) => ({
    id: `${risk}-${index}`,
    title: risk.replace(/\s+within roughly [^,]+/i, "").replace(/\.$/, ""),
    distance: extractDistance(risk) ?? sharedDistance,
    timeline: extractTimeline(risk) ?? sharedTimeline,
    confidence: result.confidence,
  }));
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

  return (
    <div className="score-hero">
      <div className="score-hero-copy">
        <p className="score-hero-kicker">Score hero</p>
        <div className="score-hero-topline">
          <p className="score-label">Disruption score</p>
          <p className="confidence-pill">Confidence level: {result.confidence}</p>
        </div>
        <div className="score-value score-value--animated">{displayScore}</div>
        <h2 className="score-hero-title">{scoreMessage.label}</h2>
        <p className="score-hero-summary">{scoreMessage.summary}</p>
      </div>

      <div className="score-hero-sidecar">
        <p className="score-meta">Trusted near-term signal for</p>
        <p className="score-hero-address">{result.address}</p>
      </div>
    </div>
  );
}

export function SeverityMeters({ severity }: SeverityMetersProps) {
  const rows = useMemo(
    () => [
      { label: "Noise", value: severity.noise, accent: "noise" },
      { label: "Traffic", value: severity.traffic, accent: "traffic" },
      { label: "Dust", value: severity.dust, accent: "dust" },
    ],
    [severity],
  );

  return (
    <div className="severity-stack">
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
        Confidence Level helps frame how specific and reliable this snapshot is.
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
          <p className="risk-card-index">Risk {index + 1}</p>
          <h3>{risk.title}</h3>
          <dl className="risk-card-meta">
            <div>
              <dt>Distance</dt>
              <dd>{risk.distance}</dd>
            </div>
            <div>
              <dt>Timeline</dt>
              <dd>{risk.timeline}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{risk.confidence}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

export function ExplanationPanel({ explanation }: ExplanationPanelProps) {
  return (
    <div className="explanation-panel card-entrance" style={{ animationDelay: "180ms" }}>
      <p className="explanation-kicker">Product insight</p>
      <p className="explanation-copy">{explanation}</p>
    </div>
  );
}
