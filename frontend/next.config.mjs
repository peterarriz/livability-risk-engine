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
