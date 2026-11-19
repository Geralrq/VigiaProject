import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Local dev only: on Vercel the `api` service owns /api.
  async rewrites() {
    return process.env.VERCEL
      ? []
      : [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
  },
};

export default nextConfig;