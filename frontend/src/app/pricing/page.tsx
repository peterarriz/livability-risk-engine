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
              <p className="brand-subtitle">Pricing</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <Link href="/">Home</Link>
            <Link href="/app">Open workspace</Link>
          </nav>
        </header>

        <section className="landing-proof-grid" aria-label="Pricing tiers">
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Free</p>
            <h2>$0 / month</h2>
            <p className="section-copy">10 address lookups and full disruption brief output.</p>
          </article>
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Pro</p>
            <h2>$49 / month</h2>
            <p className="section-copy">Unlimited lookups, exports, and deeper diligence tooling.</p>
          </article>
        </section>
      </div>
    </main>
  );
}
