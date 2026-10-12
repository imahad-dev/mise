import path from "node:path";
import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "../../"),

  async rewrites() {
    return [
      // Owner/staff API paths only
      {
        source: "/api/auth/:path*",
        destination: `${API_URL}/api/auth/:path*`,
      },
      {
        source: "/api/restaurants/:path*",
        destination: `${API_URL}/api/restaurants/:path*`,
      },
      {
        source: "/api/metrics/:path*",
        destination: `${API_URL}/api/metrics/:path*`,
      },
      // Health and debug
      {
        source: "/health",
        destination: `${API_URL}/health`,
      },
      {
        source: "/debug/sse",
        destination: `${API_URL}/debug/sse`,
      },
    ];
  },
};

export default nextConfig;
