export const ALLOWED_BULK_TIERS = [
  "pilot",
  "pro",
  "teams",
  "enterprise",
  "founder",
  "admin",
] as const;

export type BulkTier = (typeof ALLOWED_BULK_TIERS)[number];

const ALLOWED_BULK_TIER_SET = new Set<string>(ALLOWED_BULK_TIERS);

const DIRECT_TIER_KEYS = [
  "subscription_tier",
  "subscriptionTier",
  "account_tier",
  "accountTier",
  "tier",
  "tiers",
  "role",
  "roles",
  "plan",
  "plans",
] as const;

const METADATA_KEYS = [
  "publicMetadata",
  "public_metadata",
  "metadata",
  "userPublicMetadata",
  "user_public_metadata",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function normalizeBulkTier(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  return normalized.length > 0 ? normalized : null;
}

export function isBulkTierAllowed(value: unknown): value is BulkTier {
  const tier = normalizeBulkTier(value);
  return tier !== null && ALLOWED_BULK_TIER_SET.has(tier);
}

function findAllowedTier(value: unknown, depth = 0): BulkTier | null {
  if (depth > 3) return null;

  if (Array.isArray(value)) {
    for (const item of value) {
      const tier = findAllowedTier(item, depth + 1);
      if (tier) return tier;
    }
    return null;
  }

  const directTier = normalizeBulkTier(value);
  if (directTier && isBulkTierAllowed(directTier)) {
    return directTier;
  }

  if (!isRecord(value)) return null;

  for (const key of DIRECT_TIER_KEYS) {
    const tier = findAllowedTier(value[key], depth + 1);
    if (tier) return tier;
  }

  for (const key of METADATA_KEYS) {
    const tier = findAllowedTier(value[key], depth + 1);
    if (tier) return tier;
  }

  return null;
}

export function getBulkAccessTier(...sources: unknown[]): BulkTier | null {
  for (const source of sources) {
    const tier = findAllowedTier(source);
    if (tier) return tier;
  }
  return null;
}
