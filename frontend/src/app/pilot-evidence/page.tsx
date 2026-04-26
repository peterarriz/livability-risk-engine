import Link from "next/link";
import { pilotEvidence } from "@/lib/pilot-evidence-data";

function number(value: number): string {
  return value.toLocaleString("en-US");
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function labelForDimension(dimension: string): string {
  if (dimension === "sexiness") return "Commercial appeal";
  return dimension.charAt(0).toUpperCase() + dimension.slice(1);
}

export default function PilotEvidencePage() {
  const { totals, customerSegments, citySummaries, personaAudit } = pilotEvidence;
  const dimensions = Object.entries(personaAudit.dimensions);
  const topCities = citySummaries;

  return (
    <main className="page pilot-evidence-page">
      <div className="shell-container pilot-evidence-shell">
        <header className="topbar landing-topbar">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden>LR</span>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">Pilot evidence</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <Link href="/">Home</Link>
            <Link href="/app">Open workspace</Link>
            <Link href="/pricing">Pricing</Link>
          </nav>
        </header>

        <section className="pilot-hero">
          <div>
            <p className="eyebrow">Multi-month source simulation</p>
            <h1>Proof that the product gets more valuable as fresh city data arrives.</h1>
            <p className="section-copy">
              This page turns synthetic source-flow testing into a buyer-readable pilot brief:
              monthly records, configured city coverage, 50 potential-customer personas, and
              concrete paid offers tied to avoided operational pain.
            </p>
            <div className="pilot-cta-row">
              <Link className="pilot-cta pilot-cta--primary" href="/app">Run an address</Link>
              <Link className="pilot-cta pilot-cta--secondary" href="/api-docs">Review API</Link>
            </div>
          </div>
          <aside className="surface-card pilot-hero-card">
            <p className="eyebrow">Current synthetic run</p>
            <strong>{number(totals.cities)} cities</strong>
            <span>{number(totals.sourceFeeds)} configured source feeds over {totals.months} months</span>
          </aside>
        </section>

        <section className="pilot-stat-grid" aria-label="Simulation totals">
          <article className="surface-card pilot-stat-card">
            <span>New records</span>
            <strong>{number(totals.generatedRecords)}</strong>
          </article>
          <article className="surface-card pilot-stat-card">
            <span>Scenario-months</span>
            <strong>{number(totals.scenarioMonths)}</strong>
          </article>
          <article className="surface-card pilot-stat-card">
            <span>Persona-city audits</span>
            <strong>{number(personaAudit.result_count)}</strong>
          </article>
          <article className="surface-card pilot-stat-card">
            <span>Overall red-team score</span>
            <strong>{personaAudit.overall}/5</strong>
          </article>
        </section>

        <section className="pilot-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Paid wedge</p>
              <h2>Sell recurring disruption briefs and API access, not a one-time score.</h2>
              <p className="section-copy">
                The strongest first buyer is CRE due diligence, with logistics, proptech, and civic coordination
                as expansion paths once batch/API workflows are in active pilots.
              </p>
            </div>
          </div>

          <div className="pilot-offer-grid">
            {customerSegments.map((segment) => (
              <article className="surface-card pilot-offer-card" key={segment.name}>
                <div className="pilot-offer-topline">
                  <span>{segment.name}</span>
                  <strong>{money(segment.monthlyPrice)}/mo</strong>
                </div>
                <h3>{segment.paidOffer}</h3>
                <p>{segment.buyer}</p>
                <dl className="pilot-mini-metrics">
                  <div>
                    <dt>Simulated value</dt>
                    <dd>{money(segment.simulatedValue)}</dd>
                  </div>
                  <div>
                    <dt>Value:price</dt>
                    <dd>{segment.valueToPrice}x</dd>
                  </div>
                  <div>
                    <dt>Avoided events</dt>
                    <dd>{segment.avoidedEvents}</dd>
                  </div>
                </dl>
                <small>{segment.valueMetric}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="pilot-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Persona red team</p>
              <h2>50 customer-like evaluators, all six dimensions at 5/5.</h2>
              <p className="section-copy">
                Personas represent buyers and buyer-adjacent skeptics: CRE, logistics, proptech, civic operations,
                hospitality, accessibility, backend, procurement, and revenue teams.
              </p>
            </div>
          </div>
          <div className="pilot-dimension-grid">
            {dimensions.map(([dimension, score]) => (
              <article className="surface-card pilot-dimension-card" key={dimension}>
                <span>{labelForDimension(dimension)}</span>
                <strong>{score}/5</strong>
              </article>
            ))}
          </div>
        </section>

        <section className="pilot-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">City/source coverage</p>
              <h2>Every configured city source is included in the six-month synthetic flow.</h2>
              <p className="section-copy">
                The table shows all simulated cities from the current repo configuration. Higher disruption scores
                mean the synthetic inflow would trigger more urgent buyer attention.
              </p>
            </div>
          </div>
          <div className="surface-card pilot-table-card">
            <div className="pilot-table-scroll">
              <table className="pilot-table">
                <thead>
                  <tr>
                    <th>City</th>
                    <th>Sources</th>
                    <th>Records</th>
                    <th>Avg disruption</th>
                    <th>High-risk months</th>
                    <th>Source families</th>
                  </tr>
                </thead>
                <tbody>
                  {topCities.map((city) => (
                    <tr key={city.city}>
                      <td>{city.city}</td>
                      <td>{city.sources}</td>
                      <td>{number(city.generated_records)}</td>
                      <td>{city.average_disruption_score}</td>
                      <td>{city.high_risk_months}</td>
                      <td>{city.source_families.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section className="pilot-section pilot-doc-grid" aria-label="Evidence files">
          <article className="surface-card">
            <p className="eyebrow">Generated docs</p>
            <h3>Evidence pack</h3>
            <ul className="pilot-doc-list">
              <li>docs/07_adversarial_review.md</li>
              <li>docs/09_persona_red_team_audit.md</li>
              <li>docs/10_persona_red_team_results.md</li>
              <li>docs/12_data_flow_simulation_results.md</li>
            </ul>
          </article>
          <article className="surface-card">
            <p className="eyebrow">Run it again</p>
            <h3>Repeatable commands</h3>
            <pre className="pilot-command-block">node scripts/simulate-data-flow.mjs --months=6{"\n"}node scripts/run-persona-red-team.mjs</pre>
          </article>
        </section>
      </div>
    </main>
  );
}
