"use client";

const SECTIONS = [
  { id: "sources", label: "Data Sources" },
  { id: "scoring", label: "Score Calculation" },
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
          The Livability Score is a composite 0&ndash;100 index that quantifies near-term livability risk
          for any US address. This page documents the data sources, calculation method, coverage,
          and known limitations. Share it with procurement, compliance, or investment committees
          evaluating the platform.
        </p>

        {/* ── Data Sources ──────────────────────────────────────── */}
        <section id="sources" className="docs-section">
          <h2>Data Sources</h2>
          <p>
            Every score is anchored to publicly available, machine-readable government datasets.
            No proprietary or self-reported data is used. Sources are refreshed on independent schedules.
          </p>
          <table className="docs-table">
            <thead>
              <tr><th>Source</th><th>Data type</th><th>Provider</th><th>Update frequency</th></tr>
            </thead>
            <tbody>
              <tr><td>Building permits</td><td>Active construction permits</td><td>City open data portals (Socrata, CKAN, ArcGIS)</td><td>Daily</td></tr>
              <tr><td>Street closures</td><td>Lane closures, curb restrictions</td><td>CDOT / city DOTs</td><td>Daily</td></tr>
              <tr><td>Crime trends</td><td>12-month incident counts by district</td><td>City police department APIs (70+ cities)</td><td>Weekly</td></tr>
              <tr><td>School ratings</td><td>CPS performance ratings, NCES CCD</td><td>IL State Board of Education, US Dept of Education</td><td>Annually</td></tr>
              <tr><td>Census demographics</td><td>Median income, vacancy rates by tract</td><td>US Census Bureau ACS 5-year estimates</td><td>Annually</td></tr>
              <tr><td>House Price Index</td><td>Zip-code and metro HPI trends</td><td>FHFA (Federal Housing Finance Agency)</td><td>Quarterly</td></tr>
              <tr><td>Flood zones</td><td>FEMA NFHL flood hazard polygons</td><td>FEMA National Flood Hazard Layer</td><td>As published</td></tr>
              <tr><td>Transit alerts</td><td>CTA planned service disruptions</td><td>CTA GTFS-RT / alerts API</td><td>Daily</td></tr>
              <tr><td>Traffic crashes</td><td>Recent crash incidents</td><td>Chicago Open Data (85ca-t3if)</td><td>Daily</td></tr>
              <tr><td>311 requests</td><td>Potholes, water main breaks, cave-ins</td><td>Chicago 311 Open Data</td><td>Daily</td></tr>
            </tbody>
          </table>
        </section>

        {/* ── Score Calculation ──────────────────────────────────── */}
        <section id="scoring" className="docs-section">
          <h2>Score Calculation</h2>
          <p>
            The Livability Score combines five dimensions, each scored 0&ndash;100 independently
            and then weighted into the composite. Higher scores indicate better livability
            (lower risk). The disruption score is inverted: a high disruption risk
            produces a low disruption component.
          </p>

          <table className="docs-table">
            <thead>
              <tr><th>Dimension</th><th>Weight</th><th>Max points</th><th>What it captures</th></tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Disruption Risk</strong></td><td>35%</td><td>35</td>
                <td>Active construction permits, street closures, demolitions, utility outages, and traffic crashes within a 500m radius. Higher nearby disruption lowers this component.</td>
              </tr>
              <tr>
                <td><strong>Crime Trend</strong></td><td>25%</td><td>25</td>
                <td>Year-over-year change in reported crime incidents for the nearest police district. Increasing crime trends lower this component; stable or decreasing trends raise it.</td>
              </tr>
              <tr>
                <td><strong>School Rating</strong></td><td>20%</td><td>20</td>
                <td>Quality rating of the nearest school (CPS performance level or NCES percentile). Higher school quality raises this component.</td>
              </tr>
              <tr>
                <td><strong>Demographics &amp; Stability</strong></td><td>10%</td><td>10</td>
                <td>Census tract median household income (relative to metro median) and housing vacancy rate. Lower vacancy and higher relative income indicate neighborhood stability.</td>
              </tr>
              <tr>
                <td><strong>Flood &amp; Environmental</strong></td><td>10%</td><td>10</td>
                <td>FEMA flood zone classification for the address location. Addresses in minimal-risk zones score highest; those in high-risk zones score lowest.</td>
              </tr>
            </tbody>
          </table>

          <h3>Calculation steps</h3>
          <ol className="docs-steps">
            <li>Geocode the input address to latitude/longitude.</li>
            <li>Query all active projects, permits, and closures within a 500-meter radius.</li>
            <li>Compute the raw disruption score (0&ndash;100) based on impact type weights, distance decay, and signal count.</li>
            <li>Fetch the latest crime trend, school rating, census demographics, and flood zone for the address.</li>
            <li>Score each dimension on a 0&ndash;100 scale, apply the weight, and sum to produce the composite Livability Score.</li>
            <li>Determine confidence level based on signal proximity and data freshness.</li>
          </ol>
        </section>

        {/* ── Coverage ──────────────────────────────────────────── */}
        <section id="coverage" className="docs-section">
          <h2>Coverage</h2>
          <p>
            Data coverage varies by city and data type. Chicago has the deepest coverage
            as the original MVP city. Other cities have been added progressively.
          </p>

          <table className="docs-table docs-table--compact">
            <thead>
              <tr><th>Data type</th><th>Full coverage</th><th>Partial / limited</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>Building permits</td>
                <td>Chicago, NYC, LA, Philadelphia, Austin, Seattle, Denver, Portland, Baltimore, Nashville, Phoenix, Columbus, Minneapolis, Charlotte, Tucson, Greensboro, Richmond, San Antonio, Cincinnati, San Francisco, Buffalo</td>
                <td>Boston, Milwaukee, New Orleans (geocoding in progress)</td>
              </tr>
              <tr>
                <td>Crime trends</td>
                <td>70+ cities with active Socrata/ArcGIS/CKAN endpoints including: Chicago, NYC, LA, Dallas, Austin, Seattle, Denver, SF, Baltimore, Nashville, Portland, DC, OKC, Houston, Phoenix, Columbus, Minneapolis, Charlotte, and many more</td>
                <td>Cities with rolling-window data (Milwaukee: 3mo, Providence: 6mo, Oakland: 3mo). Frozen datasets: Pittsburgh, Fresno, Albuquerque</td>
              </tr>
              <tr>
                <td>School ratings</td>
                <td>Illinois (CPS performance ratings)</td>
                <td>National coverage via NCES CCD (percentile-based)</td>
              </tr>
              <tr>
                <td>Census demographics</td>
                <td>All US census tracts in counties containing active permit cities (29 counties)</td>
                <td>&mdash;</td>
              </tr>
              <tr>
                <td>FHFA House Price Index</td>
                <td>All US 5-digit ZIP codes and metro areas</td>
                <td>&mdash;</td>
              </tr>
              <tr>
                <td>FEMA flood zones</td>
                <td>Chicago metro area</td>
                <td>Expanding to all active cities</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* ── Confidence Levels ──────────────────────────────────── */}
        <section id="confidence" className="docs-section">
          <h2>Confidence Levels</h2>
          <p>
            Confidence reflects how closely the detected signals are tied to the specific address,
            <em>not</em> how severe the disruption is. A high-disruption address can still have
            HIGH confidence if the signals are physically close and well-documented.
          </p>

          <table className="docs-table">
            <thead><tr><th>Level</th><th>Criteria</th><th>Interpretation</th></tr></thead>
            <tbody>
              <tr>
                <td><strong>HIGH</strong></td>
                <td>Multiple signals within 200m, at least one with a confirmed address match or permit directly at the location</td>
                <td>The score is directly attributable to this address. Safe to use for decision-making.</td>
              </tr>
              <tr>
                <td><strong>MEDIUM</strong></td>
                <td>Signals present within 500m but none directly at the address; or a single strong signal nearby</td>
                <td>The score reflects area-level conditions. The address is likely affected but the magnitude is estimated.</td>
              </tr>
              <tr>
                <td><strong>LOW</strong></td>
                <td>Few or no signals within 500m; score is derived primarily from neighborhood-level data (crime trends, demographics)</td>
                <td>The score is a baseline estimate. Consider supplementing with an on-the-ground visit or additional data.</td>
              </tr>
            </tbody>
          </table>
        </section>

        {/* ── Limitations ───────────────────────────────────────── */}
        <section id="limitations" className="docs-section">
          <h2>Limitations</h2>
          <p>
            The Livability Score is designed to surface near-term, data-backed risks.
            It has inherent limitations that users should understand.
          </p>

          <h3>What the score does NOT capture</h3>
          <ul className="docs-limitation-list">
            <li><strong>Long-term neighborhood trajectory</strong> &mdash; The score reflects current conditions, not 5-year trends. An improving neighborhood may still score poorly during active construction.</li>
            <li><strong>Indoor quality</strong> &mdash; Building condition, maintenance, appliance age, lead paint, or pest issues are not measurable from public data.</li>
            <li><strong>Noise from non-permitted sources</strong> &mdash; Bars, nightlife, traffic noise, and neighbor behavior are not captured.</li>
            <li><strong>Subjective livability factors</strong> &mdash; Walkability feel, community character, aesthetic quality, and cultural amenities are outside scope.</li>
            <li><strong>Private development plans</strong> &mdash; Projects that haven&rsquo;t yet filed permits are invisible to the score.</li>
            <li><strong>Natural disaster risk beyond FEMA zones</strong> &mdash; Wildfire, earthquake, tornado, and extreme heat risk are not included.</li>
          </ul>

          <h3>Data freshness caveats</h3>
          <ul className="docs-limitation-list">
            <li>Some crime datasets are rolling windows (3&ndash;6 months) without historical comparison. These cities show current-period counts but no year-over-year trend.</li>
            <li>Census ACS data has a 1&ndash;2 year lag. Rapidly changing neighborhoods may not yet be reflected.</li>
            <li>School ratings are updated annually. Mid-year changes (new principals, policy shifts) are not captured until the next release.</li>
            <li>FHFA HPI data is quarterly with a ~2 month publication lag.</li>
          </ul>

          <h3>Score stability</h3>
          <p>
            Scores can change daily as new permits are filed, closures begin or end, and crime
            data updates. A 5&ndash;10 point fluctuation between lookups is normal and reflects
            genuine data changes, not model instability. Changes greater than 15 points typically
            indicate a new major signal (e.g., a multi-lane closure starting or ending).
          </p>
        </section>
      </main>
    </div>
  );
}
