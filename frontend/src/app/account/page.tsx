"use client";
/**
 * frontend/src/app/account/page.tsx
 * task: app-025
 *
 * Account page — protected by Clerk middleware (/account added to matcher).
 * Shows subscription tier and API key management panel.
 *
 * On mount: calls POST /auth/sync to ensure the user row exists in Postgres
 * (satisfies app-024 notes_for_next_agent requirement).
 */

import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiKeyRecord,
  CreateKeyResponse,
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from "@/lib/api";

// Use the Vercel proxy so /auth/sync is same-origin (no CORS with Railway).
const API_BASE = "/api/backend";

export default function AccountPage() {
  const { user, isLoaded } = useUser();
  const { getToken } = useAuth();

  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [keysError, setKeysError] = useState<string | null>(null);

  const [newKey, setNewKey] = useState<string | null>(null); // plaintext — show once
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const [revoking, setRevoking] = useState<number | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const [copied, setCopied] = useState(false);
  const [syncDone, setSyncDone] = useState(false);
  const syncAttempted = useRef(false);

  // ── Sync Clerk user to Postgres users table (app-024 / app-025) ──────────
  useEffect(() => {
    if (!isLoaded || !user || syncAttempted.current) return;
    syncAttempted.current = true;
    (async () => {
      const token = await getToken();
      fetch(`${API_BASE}/auth/sync`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          clerk_user_id: user.id,
          email: user.primaryEmailAddress?.emailAddress ?? "",
        }),
      })
        .then(() => setSyncDone(true))
        .catch(() => setSyncDone(true)); // non-fatal — proceed regardless
    })();
  }, [isLoaded, user, getToken]);

  // ── Load API keys ─────────────────────────────────────────────────────────
  const loadKeys = useCallback(async () => {
    try {
      setKeysLoading(true);
      setKeysError(null);
      const token = await getToken();
      if (!token) throw new Error("Clerk session token unavailable — try refreshing");
      const data = await listApiKeys(token);
      setKeys(data.filter((k) => k.is_active));
    } catch (e) {
      setKeysError(e instanceof Error ? e.message : "Could not load keys");
    } finally {
      setKeysLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (isLoaded && user) loadKeys();
  }, [isLoaded, user, loadKeys]);

  // ── Generate key ──────────────────────────────────────────────────────────
  async function handleGenerate() {
    try {
      setGenerating(true);
      setGenerateError(null);
      setNewKey(null);
      const token = await getToken();
      if (!token) throw new Error("Clerk session token unavailable — try refreshing");
      const result: CreateKeyResponse = await createApiKey(token);
      setNewKey(result.key);
      await loadKeys();
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : "Could not generate key");
    } finally {
      setGenerating(false);
    }
  }

  // ── Revoke key ────────────────────────────────────────────────────────────
  async function handleRevoke(keyId: number) {
    try {
      setRevoking(keyId);
      setRevokeError(null);
      const token = await getToken();
      if (!token) throw new Error("Clerk session token unavailable — try refreshing");
      await revokeApiKey(keyId, token);
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
      if (newKey) setNewKey(null); // if the just-generated key was revoked, clear it
    } catch (e) {
      setRevokeError(e instanceof Error ? e.message : "Could not revoke key");
    } finally {
      setRevoking(null);
    }
  }

  // ── Copy key to clipboard ─────────────────────────────────────────────────
  function handleCopy(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (!isLoaded) {
    return (
      <main style={{ padding: "2rem", fontFamily: "system-ui, sans-serif", color: "#f1f5f9" }}>
        <p>Loading…</p>
      </main>
    );
  }

  const tier = (user as { publicMetadata?: { subscription_tier?: string } } | null)
    ?.publicMetadata?.subscription_tier ?? "free";

  const activeKey = keys[0] ?? null;

  return (
    <main style={{ padding: "2rem 1.5rem", fontFamily: "system-ui, sans-serif", color: "#f1f5f9", maxWidth: 560, margin: "0 auto" }}>
      {/* ── Header ── */}
      <div style={{ marginBottom: "2rem" }}>
        <a href="/" style={{ fontSize: "0.8rem", color: "#94a3b8", textDecoration: "none" }}>← Back to search</a>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700, margin: "0.75rem 0 0.25rem", color: "#f8fafc" }}>
          Account
        </h1>
        <p style={{ margin: 0, fontSize: "0.85rem", color: "#94a3b8" }}>
          {user?.primaryEmailAddress?.emailAddress}
          {syncDone && (
            <span style={{ marginLeft: "0.5rem", fontSize: "0.7rem", color: "#64748b" }}>· synced</span>
          )}
        </p>
      </div>

      {/* ── Subscription tier ── */}
      <section style={{ marginBottom: "1.75rem", padding: "1rem 1.25rem", background: "#1e293b", borderRadius: 8, border: "1px solid #334155" }}>
        <p style={{ margin: "0 0 0.4rem", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b" }}>
          Subscription
        </p>
        <span style={{
          display: "inline-block",
          padding: "0.2rem 0.65rem",
          borderRadius: 4,
          fontSize: "0.8rem",
          fontWeight: 600,
          background: tier === "free" ? "#1e3a5f" : "#14532d",
          color: tier === "free" ? "#93c5fd" : "#86efac",
          border: `1px solid ${tier === "free" ? "#2563eb" : "#16a34a"}`,
          textTransform: "capitalize",
        }}>
          {tier}
        </span>
        {tier === "free" && (
          <p style={{ margin: "0.6rem 0 0", fontSize: "0.75rem", color: "#64748b" }}>
            Upgrade to Pro for higher rate limits and batch access.
          </p>
        )}
      </section>

      {/* ── API Key panel ── */}
      <section style={{ padding: "1rem 1.25rem", background: "#1e293b", borderRadius: 8, border: "1px solid #334155" }}>
        <p style={{ margin: "0 0 1rem", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b" }}>
          API Key
        </p>

        {keysLoading && (
          <p style={{ margin: 0, fontSize: "0.85rem", color: "#64748b" }}>Loading…</p>
        )}
        {keysError && (
          <p style={{ margin: 0, fontSize: "0.8rem", color: "#f87171" }}>{keysError}</p>
        )}

        {/* Newly generated plaintext key — shown once */}
        {newKey && (
          <div style={{ marginBottom: "1rem", padding: "0.75rem", background: "#0f172a", borderRadius: 6, border: "1px solid #16a34a" }}>
            <p style={{ margin: "0 0 0.4rem", fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: "#4ade80" }}>
              Your new key — copy it now, it won&apos;t be shown again
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <code style={{ flex: 1, fontSize: "0.75rem", wordBreak: "break-all", color: "#f1f5f9" }}>{newKey}</code>
              <button
                type="button"
                onClick={() => handleCopy(newKey)}
                style={{ padding: "0.3rem 0.6rem", borderRadius: 4, border: "1px solid #334155", background: copied ? "#166534" : "#1e293b", color: copied ? "#4ade80" : "#94a3b8", fontSize: "0.72rem", cursor: "pointer", whiteSpace: "nowrap" }}
              >
                {copied ? "Copied!" : "Copy"}
              </button>
            </div>
          </div>
        )}

        {/* Active key info */}
        {!keysLoading && activeKey && (
          <div style={{ marginBottom: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <code style={{ fontSize: "0.8rem", color: "#94a3b8", flex: 1 }}>{activeKey.masked_key}</code>
              <button
                type="button"
                onClick={() => handleCopy(activeKey.masked_key)}
                style={{ padding: "0.25rem 0.5rem", borderRadius: 4, border: "1px solid #334155", background: "#0f172a", color: "#64748b", fontSize: "0.7rem", cursor: "pointer" }}
              >
                Copy prefix
              </button>
            </div>
            <div style={{ fontSize: "0.75rem", color: "#64748b", display: "flex", gap: "1rem" }}>
              <span>Calls: <strong style={{ color: "#94a3b8" }}>{activeKey.call_count.toLocaleString()}</strong></span>
              {activeKey.last_called_at && (
                <span>Last used: <strong style={{ color: "#94a3b8" }}>{new Date(activeKey.last_called_at).toLocaleDateString()}</strong></span>
              )}
            </div>
          </div>
        )}

        {!keysLoading && !activeKey && !newKey && (
          <p style={{ margin: "0 0 1rem", fontSize: "0.85rem", color: "#64748b" }}>
            No active API key. Generate one to access the <code>/score</code> API programmatically.
          </p>
        )}

        {revokeError && (
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.78rem", color: "#f87171" }}>{revokeError}</p>
        )}
        {generateError && (
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.78rem", color: "#f87171" }}>{generateError}</p>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {!activeKey && (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              style={{ padding: "0.45rem 1rem", borderRadius: 5, border: "none", background: generating ? "#334155" : "#2563eb", color: "#fff", fontSize: "0.82rem", fontWeight: 600, cursor: generating ? "not-allowed" : "pointer" }}
            >
              {generating ? "Generating…" : "Generate Key"}
            </button>
          )}
          {activeKey && (
            <button
              type="button"
              onClick={() => handleRevoke(activeKey.id)}
              disabled={revoking === activeKey.id}
              style={{ padding: "0.45rem 1rem", borderRadius: 5, border: "1px solid #dc2626", background: "transparent", color: "#f87171", fontSize: "0.82rem", fontWeight: 600, cursor: revoking === activeKey.id ? "not-allowed" : "pointer" }}
            >
              {revoking === activeKey.id ? "Revoking…" : "Revoke Key"}
            </button>
          )}
        </div>

        <p style={{ margin: "1rem 0 0", fontSize: "0.72rem", color: "#475569" }}>
          Send the key as the <code>X-API-Key</code> header on each request.
        </p>
      </section>
    </main>
  );
}
