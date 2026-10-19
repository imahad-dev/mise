import path from "node:path";
import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(process.cwd(), "../../"),

  async rewrites() {
    return [
      // Guest-specific API paths
      {
        source: "/api/guest/:path*",
        destination: `${API_URL}/api/guest/:path*`,
      },
      {
        source: "/api/orders/:path*",
        destination: `${API_URL}/api/orders/:path*`,
      },
      // Auth and Demo paths for demo launcher
      {
        source: "/api/auth/:path*",
        destination: `${API_URL}/api/auth/:path*`,
      },
      {
        source: "/api/demo/:path*",
        destination: `${API_URL}/api/demo/:path*`,
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
