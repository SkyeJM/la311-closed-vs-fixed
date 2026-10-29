import type { NextConfig } from "next";

// On Vercel, vercel.json routes /api/* to the FastAPI service before Next.js sees it. Locally,
// `make serve` runs FastAPI on :8000 and this rewrite stands in for that routing (in dev, or in
// a local production build when API_DEV_ORIGIN is set).
const apiOrigin = process.env.API_DEV_ORIGIN ?? "http://127.0.0.1:8000";
const proxyApi = process.env.NODE_ENV === "development" || Boolean(process.env.API_DEV_ORIGIN);

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return proxyApi ? [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }] : [];
  },
};

export default nextConfig;
