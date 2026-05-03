import Link from "next/link";

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
          <h1 id="pricing-title">Access is by request during the design-partner pilot.</h1>
          <p className="section-copy">
            During the design-partner pilot, access is by request. Commercial pricing follows pilot validation.
          </p>
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
