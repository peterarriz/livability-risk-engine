"use client";

/**
 * Onboarding flow — 3-step modal shown to new users after sign-up.
 *
 * Step 1: User role selection
 * Step 2: Preferred city selection
 * Step 3: Analyze your first address (auto-populated example)
 *
 * Stores selections in Clerk unsafeMetadata (role, preferred_city,
 * onboarding_complete). Feature tour tooltips shown after completion.
 */

import { useCallback, useEffect, useState } from "react";
import { useUser } from "@/lib/clerk-client";

// ── City data ────────────────────────────────────────────────────────────────

const TOP_CITIES = [
  { name: "Chicago", example: "1600 W Chicago Ave, Chicago, IL" },
  { name: "New York", example: "350 5th Ave, New York, NY" },
  { name: "Los Angeles", example: "1000 Vin Scully Ave, Los Angeles, CA" },
  { name: "Dallas", example: "2200 Commerce St, Dallas, TX" },
  { name: "Houston", example: "500 Crawford St, Houston, TX" },
  { name: "Phoenix", example: "200 W Washington St, Phoenix, AZ" },
  { name: "Philadelphia", example: "237 S 18th St, Philadelphia, PA" },
  { name: "Austin", example: "1100 Congress Ave, Austin, TX" },
  { name: "Denver", example: "1701 Bryant St, Denver, CO" },
  { name: "Seattle", example: "1000 1st Ave, Seattle, WA" },
  { name: "Nashville", example: "501 Broadway, Nashville, TN" },
  { name: "San Francisco", example: "1 Dr Carlton B Goodlett Pl, San Francisco, CA" },
] as const;

const ROLES = [
  { id: "buyer_renter", label: "Home buyer / Renter", icon: "🏠" },
  { id: "agent", label: "Real estate professional", icon: "🏢" },
  { id: "investor", label: "Property investor", icon: "📊" },
  { id: "developer", label: "Developer / Builder", icon: "🔨" },
  { id: "other", label: "Other", icon: "👤" },
] as const;

// ── Tour tooltips ────────────────────────────────────────────────────────────

const TOUR_STEPS = [
  { target: ".score-card", text: "Your livability score — a 0-100 composite of disruption, crime, schools, and environment.", position: "bottom" as const },
  { target: ".risk-card-section", text: "Signal cards show the top nearby disruptions affecting your score.", position: "top" as const },
  { target: ".map-container", text: "The map shows all active signals within scoring range of your address.", position: "top" as const },
  { target: ".score-action-row", text: "The recommended action tells you what to do based on your score.", position: "bottom" as const },
] as const;

// ── Types ────────────────────────────────────────────────────────────────────

type OnboardingProps = {
  onComplete: (exampleAddress: string | null) => void;
};

// ── Component ────────────────────────────────────────────────────────────────

export function OnboardingModal({ onComplete }: OnboardingProps) {
  const { user } = useUser();
  const [step, setStep] = useState(1);
  const [role, setRole] = useState<string | null>(null);
  const [city, setCity] = useState<string | null>(null);

  const handleFinish = useCallback(async () => {
    // Save to Clerk unsafeMetadata
    if (user) {
      try {
        await user.update({
          unsafeMetadata: {
            ...(user.unsafeMetadata ?? {}),
            role,
            preferred_city: city,
            onboarding_complete: true,
          },
        });
      } catch {
        // Best-effort — don't block completion if Clerk write fails
      }
    }

    // Also save to localStorage as fallback
    try {
      localStorage.setItem("lre_onboarding_complete", "1");
      if (role) localStorage.setItem("lre_user_role", role);
      if (city) localStorage.setItem("lre_preferred_city", city);
    } catch { /* ignore */ }

    // Find example address for selected city
    const cityData = TOP_CITIES.find((c) => c.name === city);
    onComplete(cityData?.example ?? null);
  }, [user, role, city, onComplete]);

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-card">
        {/* Progress dots */}
        <div className="onboarding-progress">
          {[1, 2, 3].map((s) => (
            <span key={s} className={`onboarding-dot${s === step ? " onboarding-dot--active" : s < step ? " onboarding-dot--done" : ""}`} />
          ))}
        </div>

        {/* Step 1: Role */}
        {step === 1 && (
          <div className="onboarding-step">
            <h2>What best describes you?</h2>
            <p className="onboarding-subtitle">This helps us tailor your experience.</p>
            <div className="onboarding-role-grid">
              {ROLES.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`onboarding-role-btn${role === r.id ? " onboarding-role-btn--selected" : ""}`}
                  onClick={() => setRole(r.id)}
                >
                  <span className="onboarding-role-icon">{r.icon}</span>
                  <span>{r.label}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              className="onboarding-next-btn"
              disabled={!role}
              onClick={() => setStep(2)}
            >
              Continue
            </button>
          </div>
        )}

        {/* Step 2: City */}
        {step === 2 && (
          <div className="onboarding-step">
            <h2>What city are you most interested in?</h2>
            <p className="onboarding-subtitle">We'll start you with an example from this city.</p>
            <div className="onboarding-city-grid">
              {TOP_CITIES.map((c) => (
                <button
                  key={c.name}
                  type="button"
                  className={`onboarding-city-tile${city === c.name ? " onboarding-city-tile--selected" : ""}`}
                  onClick={() => setCity(c.name)}
                >
                  {c.name}
                </button>
              ))}
            </div>
            <div className="onboarding-btn-row">
              <button type="button" className="onboarding-back-btn" onClick={() => setStep(1)}>Back</button>
              <button
                type="button"
                className="onboarding-next-btn"
                disabled={!city}
                onClick={() => setStep(3)}
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {/* Step 3: First analysis */}
        {step === 3 && (
          <div className="onboarding-step">
            <h2>Analyze your first address</h2>
            <p className="onboarding-subtitle">
              We'll start with an example in {city ?? "your city"}. You can change this anytime.
            </p>
            <div className="onboarding-example-card">
              <p className="onboarding-example-label">Example address</p>
              <p className="onboarding-example-addr">
                {TOP_CITIES.find((c) => c.name === city)?.example ?? "1600 W Chicago Ave, Chicago, IL"}
              </p>
            </div>
            <div className="onboarding-btn-row">
              <button type="button" className="onboarding-back-btn" onClick={() => setStep(2)}>Back</button>
              <button type="button" className="onboarding-next-btn" onClick={handleFinish}>
                Get my score
              </button>
            </div>
          </div>
        )}

        {/* Skip link */}
        <button type="button" className="onboarding-skip" onClick={() => { onComplete(null); try { localStorage.setItem("lre_onboarding_complete", "1"); } catch {} }}>
          Skip for now
        </button>
      </div>
    </div>
  );
}

// ── Feature tour ─────────────────────────────────────────────────────────────

export function FeatureTour({ onDismiss }: { onDismiss: () => void }) {
  const [tourStep, setTourStep] = useState(0);

  useEffect(() => {
    // Scroll the target element into view
    const target = document.querySelector(TOUR_STEPS[tourStep]?.target ?? "");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [tourStep]);

  if (tourStep >= TOUR_STEPS.length) {
    onDismiss();
    return null;
  }

  const current = TOUR_STEPS[tourStep];
  const target = typeof document !== "undefined" ? document.querySelector(current.target) : null;
  const rect = target?.getBoundingClientRect();

  if (!rect) {
    // Target not visible yet — skip or wait
    return (
      <div className="tour-overlay">
        <div className="tour-tooltip" style={{ top: "50%", left: "50%", transform: "translate(-50%, -50%)" }}>
          <p className="tour-text">{current.text}</p>
          <div className="tour-actions">
            <span className="tour-counter">{tourStep + 1}/{TOUR_STEPS.length}</span>
            <button type="button" className="tour-next-btn" onClick={() => setTourStep((s) => s + 1)}>
              {tourStep < TOUR_STEPS.length - 1 ? "Next" : "Done"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const tooltipTop = current.position === "bottom" ? rect.bottom + 12 : rect.top - 12;
  const tooltipTransform = current.position === "bottom" ? "translateX(-50%)" : "translate(-50%, -100%)";

  return (
    <div className="tour-overlay">
      {/* Highlight ring */}
      <div
        className="tour-highlight"
        style={{
          top: rect.top - 4,
          left: rect.left - 4,
          width: rect.width + 8,
          height: rect.height + 8,
        }}
      />
      {/* Tooltip */}
      <div
        className="tour-tooltip"
        style={{
          top: tooltipTop,
          left: rect.left + rect.width / 2,
          transform: tooltipTransform,
        }}
      >
        <p className="tour-text">{current.text}</p>
        <div className="tour-actions">
          <span className="tour-counter">{tourStep + 1}/{TOUR_STEPS.length}</span>
          <button type="button" className="tour-next-btn" onClick={() => setTourStep((s) => s + 1)}>
            {tourStep < TOUR_STEPS.length - 1 ? "Next" : "Done"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Hook: should show onboarding? ────────────────────────────────────────────

export function useOnboardingState() {
  const { user, isSignedIn, isLoaded } = useUser();
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn || !user) { setShouldShow(false); return; }

    // Check Clerk unsafeMetadata first
    const meta = user.unsafeMetadata as Record<string, unknown> | undefined;
    if (meta?.onboarding_complete) { setShouldShow(false); return; }

    // Fallback: check localStorage
    try {
      if (localStorage.getItem("lre_onboarding_complete") === "1") {
        setShouldShow(false);
        return;
      }
    } catch { /* ignore */ }

    setShouldShow(true);
  }, [isLoaded, isSignedIn, user]);

  return shouldShow;
}
