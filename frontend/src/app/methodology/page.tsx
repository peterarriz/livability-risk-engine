"use client";

const SECTIONS = [
  { id: "sources", label: "Data Sources" },
  { id: "scoring", label: "Score Calculation" },
  { id: "evidence", label: "Evidence Quality" },
  { id: "coverage", label: "Coverage" },
  { id: "confidence", label: "Confidence Levels" },
  { id: "limitations", label: "Limitations" },
] as const;

export default function MethodologyPage() {
  return (
    <div className="docs-layout">
      <nav className="docs-nav" aria-label="Methodology sections">
        <p className="docs-nav-title">Methodology</p>
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="docs-nav-link">{s.label}</a>
        ))}
        <a href="/" className="docs-nav-link docs-nav-back">&larr; Back to app</a>
      </nav>

      <main className="docs-main">
        <h1 className="docs-title">Scoring Methodology</h1>
        <p className="docs-intro">
          The product scores near-term construction disruption for addresses in supported cities.
          This page documents the public sources, rule-based calculation, evidence quality,
          and known limitations for coverage-aware multi-city scoring.
        </p>

        <section id="sources" className="docs-section">
          <h2>Data Sources</h2>
          <p>
            Scores are anchored to publicly available city records. Chicago remains the
            reference market, but the scope is multi-city when source provenance and
            normalization are documented.
          </p>
          <table className="docs-table">
            <thead>
              <tr><th>Source family</th><th>Data type</th><th>Provider</th><th>Update frequency</th></tr>
            </thead>
            <tbody>
              <tr><td>Building permits</td><td>Active construction permits</td><td>City open-data portals</td><td>Source-specific daily target</td></tr>
              <tr><td>Street closures</td><td>Lane closures and curb restrictions</td><td>City transportation records</td><td>Source-specific daily target</td></tr>
              <tr><td>Related public signals</td><td>Documented disruption context</td><td>Configured public feeds</td><td>Source-specific</td></tr>
            </tbody>
          </table>
        </section>

        <section id="scoring" className="docs-section">
          <h2>Score Calculation</h2>
          <p>
            The disruption score is a rule-based 0&ndash;100 subscore where higher means more
            near-term disruption risk. The public livability score uses the approved response
            contract where higher is better and lower near-term disruption improves the score.
          </p>

          <table className="docs-table">
            <thead>
              <tr><th>Dimension</th><th>Weight</th><th>Max points</th><th>What it captures</th></tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Disruption Risk</strong></td><td>Rule-based</td><td>0&ndash;100</td>
                <td>Active construction permits and planned closures within the scoring radius. Stronger, closer, and more current signals increase disruption risk.</td>
              </tr>
            </tbody>
          </table>

          <h3>Calculation steps</h3>
          <ol className="docs-steps">
            <li>Geocode the input address to latitude/longitude.</li>
            <li>Query active projects, permits, and closures within the scoring radius.</li>
            <li>Compute the raw disruption score using impact type weights, distance decay, and time multiplier.</li>
            <li>Assign confidence and evidence quality based on signal count, proximity, source freshness, and city coverage.</li>
          </ol>
        </section>

        <section id="evidence" className="docs-section">
          <h2>Evidence Quality</h2>
          <p>
            Each score includes an evidence quality assessment that indicates how much
            address-specific data backs the result. This helps users calibrate how much
            weight to give the score.
          </p>

          <table className="docs-table">
            <thead><tr><th>Level</th><th>Criteria</th><th>What it means</th></tr></thead>
            <tbody>
              <tr><td><strong>Strong</strong></td><td>3 or more non-trivial nearby permit or closure signals</td><td>The score is well-supported by multiple address-level data points.</td></tr>
              <tr><td><strong>Moderate</strong></td><td>1-2 strong nearby signals</td><td>The score has direct evidence but limited signal density.</td></tr>
              <tr><td><strong>Limited</strong> (contextual only)</td><td>No strong address-level signals, but weak contextual evidence exists</td><td>The score is useful for screening but not final decisions.</td></tr>
              <tr><td><strong>Insufficient</strong></td><td>No strong permit or closure signals available</td><td>The score is directional only and should be supplemented with manual review.</td></tr>
            </tbody>
          </table>
        </section>

        <section id="coverage" className="docs-section">
          <h2>Coverage</h2>
          <p>
            Coverage varies by city, source, and data type. A city can be supported for
            one source family while another source remains partial or unavailable.
          </p>

          <table className="docs-table docs-table--compact">
            <thead>
              <tr><th>Data type</th><th>Full coverage means</th><th>Partial / limited means</th></tr>
            </thead>
            <tbody>
              <tr><td>Building permits</td><td>Recent permit records include usable dates, addresses, and coordinates or geocodable locations</td><td>Records without usable coordinates may not affect address-level scoring</td></tr>
              <tr><td>Street closures</td><td>Active/planned closure records include location, timing, and impact type</td><td>Street-only records can be less precise than address-level permits</td></tr>
              <tr><td>Related signals</td><td>Source is documented and normalized into the canonical project schema</td><td>Signals may be used only for context or omitted until validated</td></tr>
            </tbody>
          </table>
        </section>

        <section id="confidence" className="docs-section">
          <h2>Confidence Levels</h2>
          <p>
            Confidence reflects how closely detected signals are tied to the specific address,
            not how severe the disruption is.
          </p>

          <table className="docs-table">
            <thead><tr><th>Level</th><th>Criteria</th><th>Interpretation</th></tr></thead>
            <tbody>
              <tr><td><strong>HIGH</strong></td><td>Multiple close signals, at least one directly address-relevant</td><td>The score is directly attributable to this address.</td></tr>
              <tr><td><strong>MEDIUM</strong></td><td>Nearby signals are present but not directly tied to the address, or source coverage is partial</td><td>The score reflects area-level conditions.</td></tr>
              <tr><td><strong>LOW</strong></td><td>Few signals, sparse source coverage, or weak location precision</td><td>The score is directional and should be supplemented with manual review.</td></tr>
            </tbody>
          </table>
        </section>

        <section id="limitations" className="docs-section">
          <h2>Limitations</h2>
          <p>
            The Livability Score is designed to surface near-term, data-backed risks.
            It has inherent limitations that users should understand.
          </p>

          <h3>What the score does NOT capture</h3>
          <ul className="docs-limitation-list">
            <li><strong>Long-term neighborhood trajectory</strong> &mdash; The score reflects current conditions, not 5-year trends.</li>
            <li><strong>Indoor quality</strong> &mdash; Building condition, maintenance, appliance age, lead paint, or pest issues are not measurable from public disruption data.</li>
            <li><strong>Noise from non-permitted sources</strong> &mdash; Bars, nightlife, traffic noise, and neighbor behavior are not captured.</li>
            <li><strong>Subjective livability factors</strong> &mdash; Walkability feel, community character, aesthetic quality, and cultural amenities are outside scope.</li>
            <li><strong>Private development plans</strong> &mdash; Projects that have not filed permits are invisible to the score.</li>
            <li><strong>Real-time traffic feeds</strong> &mdash; Paid GPS and vehicle-location feeds are intentionally out of scope.</li>
          </ul>

          <h3>Coverage and freshness caveats</h3>
          <ul className="docs-limitation-list">
            <li>Coverage varies by city and source. Use evidence_quality, confidence, and confidence_reason before relying on a specific address result.</li>
            <li>Signals with passed end dates may be retained briefly because official records can lag field conditions.</li>
            <li>Public records can lag field conditions. A recently finished or newly started closure may not be reflected immediately.</li>
          </ul>
        </section>
      </main>
    </div>
  );
}
