const BUILD_ONLY_CLERK_PUBLISHABLE_KEY =
  "pk_test_ZHVtbXkuY2xlcmsuYWNjb3VudHMuZGV2JA==";

function hasValidClerkPublishableKey(value) {
  if (!value || typeof value !== "string") return false;
  const parts = value.split("_");
  if (parts.length !== 3 || !["pk_test", "pk_live"].includes(`${parts[0]}_${parts[1]}`)) {
    return false;
  }

  try {
    const decoded = Buffer.from(parts[2], "base64").toString("utf8");
    return decoded.endsWith("$") && decoded.slice(0, -1).includes(".");
  } catch {
    return false;
  }
}

const clerkPublishableKeyError =
  "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is missing or invalid. Set a valid Clerk publishable key before deploying production.";
const clerkSecretKeyError =
  "CLERK_SECRET_KEY is missing or invalid. Set a valid Clerk secret key before deploying production.";

const hasConfiguredClerkPublishableKey = hasValidClerkPublishableKey(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
) && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY !== BUILD_ONLY_CLERK_PUBLISHABLE_KEY;

process.env.NEXT_PUBLIC_CLERK_CONFIGURED = hasConfiguredClerkPublishableKey
  ? "true"
  : "false";

if (!hasConfiguredClerkPublishableKey) {
  if (process.env.VERCEL_ENV === "production") {
    throw new Error(clerkPublishableKeyError);
  }

  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = BUILD_ONLY_CLERK_PUBLISHABLE_KEY;
  console.warn(
    `${clerkPublishableKeyError} Using a build-only placeholder for local or preview builds; auth will not work until a real key is configured.`,
  );
}

if (
  process.env.VERCEL_ENV === "production" &&
  !/^sk_(test|live)_/.test(process.env.CLERK_SECRET_KEY || "")
) {
  throw new Error(clerkSecretKeyError);
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Compress responses
  compress: true,

  // Strict mode catches double-render bugs in development
  reactStrictMode: true,

  // Static asset caching headers
  async headers() {
    return [
      {
        // Immutable cache for hashed Next.js static chunks
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        // Short cache for API-driven pages — score data changes frequently
        source: "/",
        headers: [
          { key: "Cache-Control", value: "public, s-maxage=0, must-revalidate" },
        ],
      },
      {
        // Saved reports can be cached briefly at the CDN edge
        source: "/report/:id",
        headers: [
          { key: "Cache-Control", value: "public, s-maxage=60, stale-while-revalidate=300" },
        ],
      },
    ];
  },
};

export default nextConfig;
