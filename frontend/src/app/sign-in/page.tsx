"use client";

import Link from "next/link";

import { SignedIn, SignedOut, SignInButton, UserButton } from "@/lib/clerk-client";

export default function SignInPage() {
  return (
    <main className="page">
      <div className="shell-container" style={{ maxWidth: "720px" }}>
        <section className="hero-card" style={{ padding: "2rem", textAlign: "center" }}>
          <p className="score-hero-kicker">Account access</p>
          <h1 style={{ margin: "0 0 0.75rem", fontSize: "1.75rem" }}>Sign in for pilot tools</h1>
          <p style={{ margin: "0 auto 1.25rem", maxWidth: "46rem", color: "var(--text-soft)" }}>
            Public address scoring works without signing in. Use this page only for pilot API keys,
            saved account workflows, and internal demo access.
          </p>

          <SignedOut>
            <SignInButton mode="modal">
              <button type="button" className="gate-btn gate-btn--primary">
                Sign in
              </button>
            </SignInButton>
          </SignedOut>

          <SignedIn>
            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.75rem" }}>
              <UserButton afterSignOutUrl="/" />
              <Link href="/account" className="gate-btn gate-btn--primary">
                Open account
              </Link>
            </div>
          </SignedIn>

          <p style={{ marginTop: "1rem", fontSize: "0.82rem", color: "var(--text-muted)" }}>
            <Link href="/app" style={{ color: "var(--brand)", fontWeight: 600 }}>
              Continue to public scoring
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}
