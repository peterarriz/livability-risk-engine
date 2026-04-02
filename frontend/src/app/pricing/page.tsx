"use client";

import React from "react";
import { SignedIn, SignedOut, SignInButton, UserButton } from "@clerk/nextjs";

export default function PricingPage() {
  return (
    <main className="page page--explore">
      <div className="shell-container">
        {/* ── Nav bar ──────────────────────────────────────────────── */}
        <header className="shell-header topbar">
          <div className="brand-lockup">
            <a href="/" style={{ display: "flex", alignItems: "center", gap: 14, textDecoration: "none", color: "inherit" }}>
              <div className="brand-mark" aria-hidden="true">LI</div>
              <div>
                <p className="brand-title">Livability Intelligence</p>
              </div>
            </a>
          </div>
          <nav className="topnav" aria-label="Primary">
            <a href="/#how-it-works">How it works</a>
            <a href="/pricing" style={{ fontWeight: 700, color: "var(--brand)" }}>Pricing</a>
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

        {/* ── Page title ─────────────────────────────────────────── */}
        <section className="shell-section" style={{ textAlign: "center", marginTop: 48 }}>
          <p className="eyebrow">Pricing</p>
          <h1 style={{ fontSize: "clamp(2rem, 5vw, 3.2rem)", letterSpacing: "-0.04em", marginBottom: 12 }}>
            Choose the right plan
          </h1>
          <p style={{ color: "var(--text-soft)", maxWidth: 560, margin: "0 auto", lineHeight: 1.7 }}>
            Start free. Upgrade when you need more lookups, team access, or API integration.
          </p>
        </section>

        {/* ── Pricing cards ──────────────────────────────────────── */}
        <section className="shell-section pricing-section">
          <div className="pricing-grid pricing-grid--four">
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
              <p className="supporting-kicker">Free</p>
              <h2 style={{ margin: "8px 0 12px" }}>$0 / month</h2>
              <p className="pricing-roi">For exploring and occasional lookups</p>
              <ul className="pricing-features">
                <li>10 address lookups / month</li>
                <li>Real-time livability score</li>
                <li>Signal cards and confidence read</li>
                <li>Spatial map context</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--secondary">Get started free</button>
            </div>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--brand)", position: "relative" }}>
              <span style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)", background: "var(--brand)", color: "#081120", fontSize: "0.72rem", fontWeight: 700, padding: "4px 14px", borderRadius: 999, letterSpacing: "0.08em", textTransform: "uppercase" }}>Most popular</span>
              <p className="supporting-kicker">Pro</p>
              <h2 style={{ margin: "8px 0 12px" }}>$49 / month</h2>
              <p className="pricing-roi">Typical agent runs 50+ lookups/month</p>
              <ul className="pricing-features">
                <li>Unlimited address lookups</li>
                <li>30-day disruption forecasts</li>
                <li>PDF and CSV report exports</li>
                <li>Permit detail drill-down</li>
                <li>Address comparison tool</li>
                <li>Alert monitoring (email)</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--primary">Start Pro trial</button>
            </div>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
              <p className="supporting-kicker">Teams</p>
              <h2 style={{ margin: "8px 0 12px" }}>$199 / month</h2>
              <p className="pricing-roi">For brokerages and property managers</p>
              <ul className="pricing-features">
                <li>Everything in Pro</li>
                <li>Up to 5 team seats</li>
                <li>CSV bulk import (500 addresses)</li>
                <li>REST API access</li>
                <li>Team dashboard</li>
                <li>Priority support</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--primary">Start Teams trial</button>
            </div>
            <div className="surface-card" style={{ padding: "32px 24px", borderRadius: "var(--radius-lg)", border: "1px solid var(--border)" }}>
              <p className="supporting-kicker">Enterprise</p>
              <h2 style={{ margin: "8px 0 12px" }}>From $999 / month</h2>
              <p className="pricing-roi">Custom pricing for large teams</p>
              <ul className="pricing-features">
                <li>Everything in Teams</li>
                <li>Unlimited seats</li>
                <li>Batch API (10,000+ addresses/mo)</li>
                <li>Webhook alerts</li>
                <li>SLA guarantee</li>
                <li>White-label reports</li>
                <li>Dedicated account manager</li>
              </ul>
              <a
                href="mailto:enterprise@livabilityrisks.com?subject=Enterprise%20inquiry"
                className="pricing-cta pricing-cta--enterprise"
              >
                Talk to us
              </a>
            </div>
          </div>
        </section>

        {/* ── Feature comparison table ───────────────────────────── */}
        <section className="shell-section">
          <div className="pricing-comparison">
            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Free</th>
                  <th>Pro</th>
                  <th>Teams</th>
                  <th>Enterprise</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Lookups / month</td><td>10</td><td>Unlimited</td><td>Unlimited</td><td>Unlimited</td></tr>
                <tr><td>Bulk CSV upload</td><td>&mdash;</td><td>&mdash;</td><td>500 addresses</td><td>10,000+</td></tr>
                <tr><td>API access</td><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>Team seats</td><td>1</td><td>1</td><td>Up to 5</td><td>Unlimited</td></tr>
                <tr><td>PDF exports</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>Alert monitoring</td><td>&mdash;</td><td>Email</td><td>Email</td><td>Email + Webhook</td></tr>
                <tr><td>30-day forecasts</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>SLA</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>99.9%</td></tr>
                <tr><td>Support</td><td>Community</td><td>Email</td><td>Priority</td><td>Dedicated</td></tr>
              </tbody>
            </table>
          </div>
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
