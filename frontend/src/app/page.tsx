import Link from "next/link";

const EXAMPLE_ADDRESS = "1600 W Chicago Ave, Chicago, IL";
const POSITIONING = "Helps brokers spot disruption risk before tenant tours and lease commitments.";
const EXAMPLE_ADDRESSES = [
  { label: "High disruption", address: "1600 W Chicago Ave, Chicago, IL", score: "62", insight: "Traffic and curb access are the dominant short-term risk." },
  { label: "Low disruption", address: "11900 S Morgan St, Chicago, IL", score: "8", insight: "No meaningful active closure or permit pressure nearby." },
  { label: "Moderate disruption", address: "3150 N Southport Ave, Chicago, IL", score: "34", insight: "Nearby renovation activity may create manageable daytime noise." },
];

export default function LandingPage() {
  const featured = EXAMPLE_ADDRESSES[0];

  return (
    <main className="page">
      <div className="shell-container landing-shell">
        <header className="topbar landing-topbar">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden>
              LR
            </span>
            <div>
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">{POSITIONING}</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <Link href="/methodology">Docs</Link>
            <Link href="/api-access">API</Link>
            <Link href="/login">Sign in</Link>
          </nav>
        </header>

        <section className="surface-card landing-hero">
          <p className="eyebrow">1. Hero</p>
          <h1>Spot disruption risk before tenant tours and lease commitments.</h1>
          <p className="lede">
            Score a Chicago address from city permit and planned closure records, then brief clients with concrete disruption signals.
          </p>
          <form action="/app" method="get" className="landing-cta-row">
            <input
              type="text"
              name="address"
              defaultValue={EXAMPLE_ADDRESS}
              aria-label="Chicago address"
              className="lookup-input"
            />
            <button type="submit" className="button button--primary">
              Score this address
            </button>
          </form>
        </section>

        <section className="surface-card landing-proof-card" aria-label="Example result">
          <p className="eyebrow">2. Example result</p>
          <h2>{featured.label} example: {featured.address}</h2>
          <p className="section-copy">Disruption score: <strong>{featured.score}</strong> · {featured.insight}</p>
          <div className="landing-example-row">
            <p className="example-label">Try an example</p>
            <div className="example-chip-group">
              {EXAMPLE_ADDRESSES.map((example) => (
                <Link
                  key={example.address}
                  className="example-chip"
                  href={`/app?address=${encodeURIComponent(example.address)}`}
                >
                  {example.label} · {example.address}
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section id="proof" className="landing-proof-grid" aria-label="Proof points">
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">3. Proof</p>
            <h2>High-risk addresses show multiple nearby disruptions</h2>
            <p className="section-copy">
              At 1600 W Chicago Ave, the brief surfaces a high-band score (62) with active closure/construction pressure near the address.
            </p>
          </article>
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Decision impact</p>
            <h2>Low-risk addresses clear faster for tours</h2>
            <p className="section-copy">
              At 11900 S Morgan St, the score drops to 8 with low severity signals, making near-term showings easier to schedule.
            </p>
          </article>
        </section>

        <section id="how-it-works" className="landing-proof-grid" aria-label="How it works">
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">4. How it works</p>
            <h2>Enter one address and get score + severity in one response</h2>
            <p className="section-copy">Each lookup returns disruption score, confidence, top drivers, and map context in the same brief.</p>
          </article>
          <article className="surface-card landing-proof-card">
            <p className="eyebrow">Interpret</p>
            <h2>Choose the next action from concrete output</h2>
            <p className="section-copy">High traffic severity means reschedule peak-hour tours; low severity means prioritize the listing this week.</p>
          </article>
        </section>

        <section className="surface-card landing-hero" aria-label="Final call to action">
          <p className="eyebrow">5. CTA</p>
          <h2>Run two listings in 30 seconds and compare risk immediately.</h2>
          <p className="section-copy">Open the workspace and test one high-risk and one low-risk address before your next broker call.</p>
          <p className="section-copy">
            <Link href="/app">Open /app →</Link>
          </p>
        </section>
      </div>
    </main>
  );
}
