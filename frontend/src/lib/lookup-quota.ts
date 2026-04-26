/**
 * lookup-quota.ts — Demo lookup gating.
 *
 * Tracks address lookups per calendar month in localStorage.
 * - Signed-in demo users: configured monthly lookup window
 * - Signed-out users: smaller monthly lookup window, then sign-up prompt
 * - Pilot-enabled users: local demo gate is disabled
 *
 * Demo/example addresses are never counted.
 */

const STORAGE_KEY = "lre_lookup_count";
const FREE_LIMIT = 10;
const ANON_LIMIT = 3;

type StoredQuota = {
  month: string;  // "2026-03"
  count: number;
};

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function readQuota(): StoredQuota {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { month: currentMonth(), count: 0 };
    const parsed: StoredQuota = JSON.parse(raw);
    // Reset if month has changed
    if (parsed.month !== currentMonth()) {
      return { month: currentMonth(), count: 0 };
    }
    return parsed;
  } catch {
    return { month: currentMonth(), count: 0 };
  }
}

function writeQuota(quota: StoredQuota): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(quota));
  } catch {
    // quota exceeded — ignore
  }
}

/** Get current lookup count and limit for this month. */
export function getLookupUsage(isSignedIn: boolean, isPro: boolean): {
  count: number;
  limit: number;
  remaining: number;
  isGated: boolean;
} {
  if (isPro) {
    return { count: 0, limit: Infinity, remaining: Infinity, isGated: false };
  }
  const quota = readQuota();
  const limit = isSignedIn ? FREE_LIMIT : ANON_LIMIT;
  return {
    count: quota.count,
    limit,
    remaining: Math.max(0, limit - quota.count),
    isGated: quota.count >= limit,
  };
}

/** Increment the lookup counter. Returns updated usage. */
export function recordLookup(isSignedIn: boolean, isPro: boolean): ReturnType<typeof getLookupUsage> {
  if (isPro) {
    return { count: 0, limit: Infinity, remaining: Infinity, isGated: false };
  }
  const quota = readQuota();
  if (quota.month !== currentMonth()) {
    quota.month = currentMonth();
    quota.count = 0;
  }
  quota.count += 1;
  writeQuota(quota);
  const limit = isSignedIn ? FREE_LIMIT : ANON_LIMIT;
  return {
    count: quota.count,
    limit,
    remaining: Math.max(0, limit - quota.count),
    isGated: quota.count >= limit,
  };
}

/** Check if an address is a demo/example (never gated). */
export function isDemoAddress(address: string): boolean {
  const normalized = address.toLowerCase().trim();
  return (
    normalized.includes("1600 w chicago") ||
    normalized.includes("700 w grand") ||
    normalized.includes("233 s wacker") ||
    normalized === "" ||
    normalized.startsWith("demo:") ||
    normalized.startsWith("example:")
  );
}
