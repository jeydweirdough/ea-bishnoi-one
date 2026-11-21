import type { NextConfig } from "next";

// The FastAPI service. The browser always calls same-origin /api/*, so cookies flow
// and no CORS is needed; Next forwards to the API. Read at build time: the Docker build
// sets API_URL=http://api:8000 (the API container on the private network).
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "same-origin" },
  // Camera: "Take photo" uses the phone camera through file inputs. Nothing else is needed.
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=(self), payment=(), usb=()" },
  ...(process.env.NODE_ENV === "production" ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  // Production image: a self-contained server (Dockerfile copies .next/standalone).
  output: "standalone",
  poweredByHeader: false,
  // Each build gets its own id so open tabs can tell a newer deploy is live (see components/service-worker.tsx).
  env: { NEXT_PUBLIC_BUILD_ID: process.env.SOURCE_COMMIT || String(Date.now()) },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Every screen sits behind sign-in: AuthGate shows the page only once the browser knows who is
    // signed in, so the server-side check for instant navigation never sees the page itself and
    // flags it as "dropped from rendering". Check only pages that ask for it (export const instant).
    instantInsights: { validationLevel: "manual-warning" },
  },
  // Screens that only repeated what each record's own page shows were merged (Nov 2026); old links still land.
  async redirects() {
    return [
      { source: "/assets/transfers", destination: "/assets/registry", permanent: false },
      { source: "/fleet/pms-repairs", destination: "/fleet/vehicles", permanent: false },
      { source: "/compliance/renewal-calendar", destination: "/dashboard/upcoming-renewals", permanent: false },
      { source: "/compliance/documents", destination: "/compliance/registrations", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
