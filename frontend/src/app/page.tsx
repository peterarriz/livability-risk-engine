"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef } from "react";
import AddressAutocomplete from "@/components/address-autocomplete";

const EXAMPLE_ADDRESS = "1600 W Chicago Ave, Chicago, IL";
const EXAMPLE_ADDRESSES = [
  { label: "Active road closures", address: "1600 W Chicago Ave, Chicago, IL", score: "62", insight: "Traffic and curb access are the dominant short-term risk." },
  { label: "Low disruption area", address: "233 S Wacker Dr, Chicago, IL", score: "12", insight: "No meaningful active closure or permit pressure nearby." },
  { label: "Construction-heavy zone", address: "700 W Grand Ave, Chicago, IL", score: "48", insight: "Nearby construction activity may create manageable daytime noise." },
];

const font = "Inter, system-ui, -apple-system, sans-serif";

export default function LandingPage() {
  const featured = EXAMPLE_ADDRESSES[0];
  const router = useRouter();
  const heroAddrRef = useRef(EXAMPLE_ADDRESS);
  const ctaAddrRef = useRef("");

  return (
    <main style={{ background: "#FFFFFF", minHeight: "100vh", position: "relative", zIndex: 1, fontFamily: font, color: "#111827" }}>

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0.75rem 2rem", borderBottom: "1px solid #E5E7EB", background: "#FFFFFF",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: "2rem", height: "2rem", borderRadius: "8px",
            background: "#2563EB", color: "#FFFFFF", fontWeight: 700, fontSize: "0.75rem",
            letterSpacing: "0.05em",
          }}>LR</span>
          <span style={{ fontWeight: 600, fontSize: "1rem", color: "#111827" }}>Livability Risk Engine</span>
        </div>
        <nav style={{ display: "flex", alignItems: "center", gap: "1.5rem", fontSize: "0.875rem" }}>
          <Link href="/methodology" style={{ color: "#6B7280", textDecoration: "none" }}>Docs</Link>
          <Link href="/api-docs" style={{ color: "#6B7280", textDecoration: "none" }}>API</Link>
        </nav>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section style={{ maxWidth: "680px", margin: "0 auto", padding: "4rem 1.5rem 2.5rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "2.25rem", fontWeight: 600, lineHeight: 1.25, color: "#111827", margin: "0 0 1rem" }}>
          Know what&rsquo;s happening at any US address before you commit.
        </h1>
        <p style={{ fontSize: "1.05rem", lineHeight: 1.6, color: "#6B7280", margin: "0 0 2rem" }}>
          Built from public permit, closure, crime, school, and flood datasets. Best for near-term address screening in major US metros. Coverage varies by city.
        </p>
        <form onSubmit={(e) => { e.preventDefault(); const a = heroAddrRef.current.trim(); if (a) router.push(`/app?address=${encodeURIComponent(a)}`); }} style={{ display: "flex", gap: "0.5rem", maxWidth: "520px", margin: "0 auto" }}>
          <AddressAutocomplete
            defaultValue={EXAMPLE_ADDRESS}
            onSelect={(a) => { heroAddrRef.current = a; }}
            onChange={(a) => { heroAddrRef.current = a; }}
            ariaLabel="US address"
            inputStyle={{
              flex: 1, padding: "0.65rem 0.9rem", fontSize: "0.9rem",
              border: "1px solid #D1D5DB", borderRadius: "8px", outline: "none",
              color: "#111827", background: "#FFFFFF", fontFamily: font,
            }}
          />
          <button type="submit" style={{
            padding: "0.65rem 1.25rem", fontSize: "0.875rem", fontWeight: 600,
            background: "#2563EB", color: "#FFFFFF", border: "none", borderRadius: "8px",
            cursor: "pointer", fontFamily: font, whiteSpace: "nowrap",
          }}>
            Analyze address
          </button>
        </form>
        <p style={{ fontSize: "0.78rem", color: "#9CA3AF", marginTop: "0.75rem" }}>
          Free tier: 10 lookups/month. No credit card required.
        </p>
      </section>

      {/* ── Trust bar ────────────────────────────────────────────────────── */}
      <div style={{
        display: "flex", justifyContent: "center", gap: "2.5rem", flexWrap: "wrap",
        padding: "1rem 1.5rem", background: "#F9FAFB",
        borderTop: "1px solid #E5E7EB", borderBottom: "1px solid #E5E7EB",
        fontSize: "0.82rem", color: "#6B7280",
      }}>
        <span><strong style={{ color: "#111827" }}>75+ cities</strong> with crime data</span>
        <span><strong style={{ color: "#111827" }}>270K+</strong> data points</span>
        <span><strong style={{ color: "#111827" }}>20+</strong> public data sources</span>
        <span><strong style={{ color: "#111827" }}>Daily</strong> updates</span>
      </div>

      {/* ── Example result ───────────────────────────────────────────────── */}
      <section style={{ maxWidth: "720px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>
        <div style={{
          background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: "12px",
          padding: "1.5rem",
        }}>
          <p style={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#9CA3AF", marginBottom: "0.5rem" }}>
            Example result
          </p>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 600, color: "#111827", margin: "0 0 0.5rem" }}>
            {featured.label}: {featured.address}
          </h2>
          <p style={{ fontSize: "0.9rem", color: "#6B7280", margin: "0 0 1.25rem", lineHeight: 1.5 }}>
            Livability score: <strong style={{ color: "#111827" }}>{featured.score}</strong> &middot; {featured.insight}
          </p>
          <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "#9CA3AF", marginBottom: "0.5rem" }}>Try an example</p>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
            {EXAMPLE_ADDRESSES.map((example) => (
              <Link
                key={example.address}
                href={`/app?address=${encodeURIComponent(example.address)}`}
                style={{
                  display: "flex", flexDirection: "column", gap: "2px",
                  padding: "0.5rem 0.75rem", borderRadius: "8px",
                  border: "1px solid #E5E7EB", textDecoration: "none", background: "#FFFFFF",
                }}
              >
                <span style={{ fontSize: "0.68rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "#9CA3AF" }}>
                  {example.label}
                </span>
                <span style={{ fontSize: "0.82rem", fontWeight: 500, color: "#374151" }}>
                  {example.address}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ── Use cases ────────────────────────────────────────────────────── */}
      <section style={{ maxWidth: "960px", margin: "0 auto", padding: "1rem 1.5rem 2.5rem" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "1rem" }}>
          {[
            { eyebrow: "Due diligence", title: "Screen addresses before tours", body: "Screen any address for active disruption before scheduling tours or recommending terms." },
            { eyebrow: "Portfolio monitoring", title: "Track conditions across addresses", body: "Monitor addresses in your portfolio. Get notified when new permits, closures, or crime trends appear." },
            { eyebrow: "Logistics", title: "Plan around active closures", body: "Check for lane closures and construction before routing teams or scheduling deliveries." },
          ].map((card) => (
            <article key={card.eyebrow} style={{
              background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: "12px",
              padding: "1.25rem",
            }}>
              <p style={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#2563EB", marginBottom: "0.4rem" }}>
                {card.eyebrow}
              </p>
              <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "#111827", margin: "0 0 0.5rem" }}>{card.title}</h3>
              <p style={{ fontSize: "0.875rem", color: "#6B7280", lineHeight: 1.55, margin: 0 }}>{card.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section style={{ background: "#F9FAFB", borderTop: "1px solid #E5E7EB", borderBottom: "1px solid #E5E7EB" }}>
        <div style={{ maxWidth: "960px", margin: "0 auto", padding: "2.5rem 1.5rem", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.5rem" }}>
          <div>
            <p style={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#9CA3AF", marginBottom: "0.5rem" }}>
              How it works
            </p>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 600, color: "#111827", margin: "0 0 0.5rem" }}>
              Enter one address and get score + severity in one response
            </h3>
            <p style={{ fontSize: "0.875rem", color: "#6B7280", lineHeight: 1.55, margin: 0 }}>
              Permits, street closures, crime trends, school ratings, flood zones, and census data — queried in real time within 500 meters of the address.
            </p>
          </div>
          <div>
            <p style={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#9CA3AF", marginBottom: "0.5rem" }}>
              Interpret
            </p>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 600, color: "#111827", margin: "0 0 0.5rem" }}>
              Choose the next action from concrete output
            </h3>
            <p style={{ fontSize: "0.875rem", color: "#6B7280", lineHeight: 1.55, margin: 0 }}>
              High traffic severity means reschedule peak-hour tours; low severity means prioritize the listing this week.
            </p>
          </div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section style={{ background: "#EFF6FF" }}>
        <div style={{ maxWidth: "600px", margin: "0 auto", padding: "3rem 1.5rem", textAlign: "center" }}>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 600, color: "#111827", margin: "0 0 0.5rem" }}>
            Run two listings in 30 seconds and compare risk immediately.
          </h2>
          <p style={{ fontSize: "0.95rem", color: "#6B7280", margin: "0 0 1.5rem" }}>
            No signup required. Results in under 10 seconds.
          </p>
          <form onSubmit={(e) => { e.preventDefault(); const a = ctaAddrRef.current.trim(); if (a) router.push(`/app?address=${encodeURIComponent(a)}`); }} style={{ display: "flex", gap: "0.5rem", maxWidth: "480px", margin: "0 auto" }}>
            <AddressAutocomplete
              placeholder="Enter any US address…"
              onSelect={(a) => { ctaAddrRef.current = a; }}
              onChange={(a) => { ctaAddrRef.current = a; }}
              ariaLabel="US address"
              inputStyle={{
                flex: 1, padding: "0.65rem 0.9rem", fontSize: "0.9rem",
                border: "1px solid #BFDBFE", borderRadius: "8px", outline: "none",
                color: "#111827", background: "#FFFFFF", fontFamily: font,
              }}
            />
            <button type="submit" style={{
              padding: "0.65rem 1.25rem", fontSize: "0.875rem", fontWeight: 600,
              background: "#2563EB", color: "#FFFFFF", border: "none", borderRadius: "8px",
              cursor: "pointer", fontFamily: font, whiteSpace: "nowrap",
            }}>
              Analyze address
            </button>
          </form>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: "1px solid #E5E7EB", padding: "1.5rem 2rem",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: "1rem", fontSize: "0.78rem", color: "#9CA3AF",
      }}>
        <span>&copy; {new Date().getFullYear()} Livability Risk Engine</span>
        <nav style={{ display: "flex", gap: "1.25rem" }}>
          <Link href="/methodology" style={{ color: "#9CA3AF", textDecoration: "none" }}>Methodology</Link>
          <Link href="/api-docs" style={{ color: "#9CA3AF", textDecoration: "none" }}>API Docs</Link>
          <Link href="/pricing" style={{ color: "#9CA3AF", textDecoration: "none" }}>Pricing</Link>
        </nav>
      </footer>
    </main>
  );
}
