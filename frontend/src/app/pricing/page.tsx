import Link from "next/link";

const PILOT_ACCESS_OPTIONS = [
  {
    title: "Public demos",
    bullets: [
      "Single-address scoring is available for evaluation and demos.",
      "Best for quick screening and product review.",
      "No account plan is required.",
    ],
  },
  {
    title: "Design-partner pilot",
    bullets: [
      "For real estate, brokerage, property management, operations, or data teams evaluating LRE on real workflows.",
      "Includes guided onboarding, selected Bulk CSV access, and feedback cycles.",
      "Pricing is scoped case-by-case during pilot validation.",
    ],
  },
  {
    title: "API / data partner access",
    bullets: [
      "For teams integrating address scoring into internal tools, underwriting workflows, or data products.",
      "API access is reviewed and provisioned by request.",
      "Raw technical API integrations use X-API-Key.",
    ],
  },
];

export default function PricingPage() {
  return (
    <main className="page">
      <div className="shell-container landing-shell">
        <header className="topbar landing-topbar">
          <Link href="/" className="brand-lockup" aria-label="Livability Risk Engine home">
            <span className="brand-mark" aria-hidden="true">LR</span>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">Design-partner pilot</p>
            </div>
          </Link>
          <nav className="topnav" aria-label="Primary">
            <Link href="/api-docs">Docs</Link>
            <Link href="/api-access">API</Link>
            <Link href="/bulk">Bulk CSV</Link>
            <Link href="/methodology">Methodology</Link>
          </nav>
        </header>

        <section className="pricing-pilot-page" aria-labelledby="pricing-title">
          <p className="eyebrow">Pilot pricing</p>
          <h1 id="pricing-title">Pilot pricing</h1>
          <p className="section-copy">
            Access is by request during the design-partner pilot. Commercial pricing follows pilot validation.
          </p>
          <div className="pricing-pilot-grid" aria-label="Pilot access options">
            {PILOT_ACCESS_OPTIONS.map((option) => (
              <article key={option.title} className="pricing-pilot-card">
                <h2>{option.title}</h2>
                <ul>
                  {option.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
          <div className="pricing-pilot-actions">
            <Link href="/api-access#pilot-bulk-access" className="pricing-cta pricing-cta--primary">
              Request pilot access
            </Link>
            <Link href="/app" className="pricing-cta pricing-cta--secondary">
              Try address scoring
            </Link>
          </div>
        </section>
      </div>
    </main>
  );
}
