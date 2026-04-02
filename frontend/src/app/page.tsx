"use client";

import React, { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/nextjs";

export default function LandingPage() {
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [ctaAddress, setCtaAddress] = useState("");

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (address.trim()) {
      router.push(`/score?address=${encodeURIComponent(address.trim())}`);
    }
  }

  function handleCtaSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (ctaAddress.trim()) {
      router.push(`/score?address=${encodeURIComponent(ctaAddress.trim())}`);
    }
  }

  return (
    <main className="page page--explore">
      {/* ── Nav bar ──────────────────────────────────────────────── */}
      <div className="shell-container">
        <header className="shell-header topbar">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">LI</div>
            <div>
              <p className="brand-title">Livability Intelligence</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <a href="#how-it-works">How it works</a>
            <a href="/pricing">Pricing</a>
            <a href="/api-docs">Docs</a>
            <SignedOut>
              <SignInButton mode="modal">
                <button type="button" className="topnav-sign-in">Sign In</button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </nav>
        </header>

        {/* ── Hero section ───────────────────────────────────────── */}
        <section className="hero-section" style={{ marginTop: 48 }}>
          <div className="surface-card surface-card--hero hero-card" style={{ textAlign: "center" }}>
            <div className="hero-copy">
              <p className="eyebrow">Address Intelligence Platform</p>
              <h1>Know what&rsquo;s happening at any US address before you commit.</h1>
              <p className="lede">
                Construction permits, crime trends, school ratings, flood risk, and price appreciation &mdash; scored 0&ndash;100 in seconds.
              </p>
            </div>

            <form className="lookup-form" onSubmit={handleSearch}>
              <div className="search-shell">
                <div className="search-input-stack">
                  <input
                    type="text"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder="Search any US address"
                    required
                  />
                </div>
                <button type="submit">Analyze address</button>
              </div>
              <div className="hero-support">
                <p className="form-hint" style={{ marginTop: 12 }}>
                  Free tier: 10 lookups/month. No credit card required.
                </p>
              </div>
            </form>
          </div>
        </section>

        {/* ── Trust bar ──────────────────────────────────────────── */}
        <section style={{ display: "flex", justifyContent: "center", gap: 40, flexWrap: "wrap", margin: "48px 0", opacity: 0.7 }}>
          {["Nationwide coverage", "270K+ data points", "20+ live data sources", "Updated daily"].map((stat) => (
            <span key={stat} style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-soft)", letterSpacing: "0.04em" }}>
              {stat}
            </span>
          ))}
        </section>

        {/* ── How it works ───────────────────────────────────────── */}
        <section className="shell-section how-it-works-section" id="how-it-works">
          <div className="section-heading">
            <div>
              <p className="eyebrow">How it works</p>
              <h2>From address to livability brief in seconds</h2>
              <p className="section-copy">Three steps. No account required.</p>
            </div>
          </div>
          <div className="how-it-works-grid">
            <div className="hiw-step">
              <div className="hiw-step-number" aria-hidden="true">01</div>
              <h3 className="hiw-step-title">Enter any address</h3>
              <p className="hiw-step-body">
                Type a street address in any supported US city. We geocode it instantly and anchor every data source to the exact location.
              </p>
            </div>
            <div className="hiw-step">
              <div className="hiw-step-number" aria-hidden="true">02</div>
              <h3 className="hiw-step-title">We analyze 20+ sources</h3>
              <p className="hiw-step-body">
                Construction permits, street closures, crime trends, school ratings, flood zones, census demographics &mdash; all queried in real time and scored within a 500-meter radius.
              </p>
            </div>
            <div className="hiw-step">
              <div className="hiw-step-number" aria-hidden="true">03</div>
              <h3 className="hiw-step-title">Get your livability brief</h3>
              <p className="hiw-step-body">
                A 0&ndash;100 livability score, severity read across noise, traffic, and construction, the strongest nearby signals, and a plain-English explanation &mdash; ready to share or export.
              </p>
            </div>
          </div>
        </section>

        {/* ── Use cases ──────────────────────────────────────────── */}
        <section className="shell-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Use cases</p>
              <h2>Built for teams that need to know before they move</h2>
            </div>
          </div>
          <div className="value-prop-grid">
            <div className="value-prop-tile">
              <h3>Real estate due diligence</h3>
              <p>Score any address before a lease signing, purchase, or investment. Surface construction, crime, school, and environmental risks that aren&rsquo;t in the listing.</p>
            </div>
            <div className="value-prop-tile">
              <h3>Portfolio risk monitoring</h3>
              <p>Track livability scores across your entire portfolio. Get alerted when new construction permits, crime trends, or infrastructure changes affect your properties.</p>
            </div>
            <div className="value-prop-tile">
              <h3>Logistics &amp; operations</h3>
              <p>Assess access disruptions before routing, scheduling deliveries, or planning site visits. Know about lane closures and construction before your team arrives.</p>
            </div>
          </div>
        </section>

        {/* ── Pricing teaser ─────────────────────────────────────── */}
        <section className="shell-section pricing-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Pricing</p>
              <h2>Simple, transparent pricing</h2>
            </div>
          </div>
          <div className="pricing-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)" }}>
              <p className="supporting-kicker">Free</p>
              <h2 style={{ fontSize: "2rem", margin: "8px 0 12px" }}>$0</h2>
              <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>10 lookups/month. No credit card.</p>
            </div>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--brand)" }}>
              <p className="supporting-kicker">Pro &mdash; Most popular</p>
              <h2 style={{ fontSize: "2rem", margin: "8px 0 12px" }}>$49<span style={{ fontSize: "1rem", color: "var(--text-soft)" }}>/mo</span></h2>
              <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>Unlimited lookups, exports, forecasts.</p>
            </div>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)" }}>
              <p className="supporting-kicker">Enterprise</p>
              <h2 style={{ fontSize: "2rem", margin: "8px 0 12px" }}>From $999<span style={{ fontSize: "1rem", color: "var(--text-soft)" }}>/mo</span></h2>
              <p style={{ color: "var(--text-soft)", fontSize: "0.9rem" }}>Batch API, SLA, dedicated support.</p>
            </div>
          </div>
          <p style={{ textAlign: "center", marginTop: 20 }}>
            <a href="/pricing" style={{ color: "var(--brand)", fontWeight: 600 }}>View full pricing &rarr;</a>
          </p>
        </section>

        {/* ── CTA ────────────────────────────────────────────────── */}
        <section className="shell-section" style={{ textAlign: "center", padding: "64px 0" }}>
          <h2 style={{ fontSize: "clamp(1.6rem, 4vw, 2.4rem)", letterSpacing: "-0.03em", marginBottom: 24 }}>
            Ready to see what&rsquo;s happening at your address?
          </h2>
          <form className="lookup-form" onSubmit={handleCtaSearch} style={{ maxWidth: 640, margin: "0 auto" }}>
            <div className="search-shell">
              <div className="search-input-stack">
                <input
                  type="text"
                  value={ctaAddress}
                  onChange={(e) => setCtaAddress(e.target.value)}
                  placeholder="Search any US address"
                  required
                />
              </div>
              <button type="submit">Analyze address</button>
            </div>
          </form>
        </section>

        {/* ── Footer ─────────────────────────────────────────────── */}
        <footer style={{ borderTop: "1px solid var(--border)", padding: "32px 0", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, fontSize: "0.85rem", color: "var(--text-muted)" }}>
          <span>&copy; 2026 Livability Intelligence</span>
          <nav style={{ display: "flex", gap: 20 }}>
            <a href="/api-docs" style={{ color: "var(--text-soft)" }}>API Docs</a>
            <a href="/methodology" style={{ color: "var(--text-soft)" }}>Methodology</a>
            <a href="mailto:enterprise@livabilityrisks.com" style={{ color: "var(--text-soft)" }}>Enterprise</a>
          </nav>
        </footer>
      </div>
    </main>
  );
}
