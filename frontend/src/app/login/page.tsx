"use client";

/**
 * frontend/src/app/login/page.tsx
 * task: data-045
 *
 * Sign-in / create account page.
 * Supports:
 *   - Google OAuth (one-click via NextAuth)
 *   - Email + password sign-in
 *   - Email + password account registration (toggled inline)
 */

import { signIn, useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status } = useSession();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Redirect already-signed-in users back to the app
  useEffect(() => {
    if (status === "authenticated") {
      const callbackUrl = searchParams.get("callbackUrl") ?? "/";
      router.replace(callbackUrl);
    }
  }, [status, router, searchParams]);

  if (status === "loading" || status === "authenticated") {
    return <div className="auth-loading">Loading…</div>;
  }

  async function handleEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    const result = await signIn("credentials", {
      email,
      password,
      mode,
      redirect: false,
    });

    setIsLoading(false);

    if (result?.error) {
      setError(result.error);
    } else {
      const callbackUrl = searchParams.get("callbackUrl") ?? "/";
      router.replace(callbackUrl);
    }
  }

  function handleGoogleSignIn() {
    const callbackUrl = searchParams.get("callbackUrl") ?? "/";
    signIn("google", { callbackUrl });
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        {/* Brand */}
        <div className="auth-brand">
          <span className="auth-brand-dot" />
          Livability Risk Engine
        </div>

        <h1 className="auth-heading">
          {mode === "login" ? "Sign in" : "Create your account"}
        </h1>
        <p className="auth-subhead">
          {mode === "login"
            ? "Access your saved addresses and alert settings."
            : "Save reports, set alerts, and track addresses over time."}
        </p>

        {/* Google OAuth button */}
        <button
          type="button"
          className="auth-btn-google"
          onClick={handleGoogleSignIn}
          disabled={isLoading}
        >
          <GoogleIcon />
          Continue with Google
        </button>

        <div className="auth-divider">
          <span>or</span>
        </div>

        {/* Email + password form */}
        <form className="auth-form" onSubmit={handleEmailSubmit} noValidate>
          {mode === "register" && (
            <label className="auth-label">
              Name (optional)
              <input
                type="text"
                className="auth-input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
              />
            </label>
          )}

          <label className="auth-label">
            Email address
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </label>

          <label className="auth-label">
            Password
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              required
              minLength={mode === "register" ? 8 : undefined}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
            />
          </label>

          {error && <p className="auth-error" role="alert">{error}</p>}

          <button
            type="submit"
            className="auth-btn-primary"
            disabled={isLoading}
          >
            {isLoading
              ? "Please wait…"
              : mode === "login"
              ? "Sign in"
              : "Create account"}
          </button>
        </form>

        {/* Toggle between sign-in / register */}
        <p className="auth-toggle">
          {mode === "login" ? (
            <>
              Don&apos;t have an account?{" "}
              <button
                type="button"
                className="auth-toggle-btn"
                onClick={() => { setMode("register"); setError(null); }}
              >
                Create one
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                type="button"
                className="auth-toggle-btn"
                onClick={() => { setMode("login"); setError(null); }}
              >
                Sign in
              </button>
            </>
          )}
        </p>

        <p className="auth-legal">
          By continuing you agree to our{" "}
          <a href="/terms" className="auth-link">Terms</a> and{" "}
          <a href="/privacy" className="auth-link">Privacy Policy</a>.
        </p>
      </div>
    </main>
  );
}

/** Minimal Google "G" SVG icon */
function GoogleIcon() {
  return (
    <svg
      className="auth-google-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      width="18"
      height="18"
    >
      <path
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        fill="#4285F4"
      />
      <path
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        fill="#34A853"
      />
      <path
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
        fill="#FBBC05"
      />
      <path
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        fill="#EA4335"
      />
    </svg>
  );
}

// Wrap in Suspense because useSearchParams() requires it in the App Router
export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-loading">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
