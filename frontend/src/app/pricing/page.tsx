import Link from "next/link";

export default function PricingPage() {
  return (
    <main className="page">
      <div className="shell-container landing-shell">
        <header className="topbar landing-topbar">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden>LR</span>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">Pilot access</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <Link href="/">Home</Link>
            <Link href="/pilot-evidence">Pilot evidence</Link>
            <Link href="/app">Open workspace</Link>
          </nav>
        </header>

        <section className="landing-proof-grid" aria-label="Pilot access options">
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Design partner pilot</p>
            <h2>API access by request</h2>
            <p className="section-copy">Founder-led pilots include API keys, onboarding, and manually monitored usage.</p>
          </article>
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Commercial roadmap</p>
            <h2>Planned self-serve tiers</h2>
            <p className="section-copy">Usage-based and team plans are planned after pilot validation and billing enforcement.</p>
          </article>
        </section>
      </div>
    </main>
  );
}
