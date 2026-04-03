import type { NextConfig } from "next";

function normalizeApiOrigin(rawUrl?: string): string {
  if (!rawUrl) {
    return "http://localhost:8000";
  }

  return rawUrl
    .trim()
    .replace(/\/+$/, "")
    .replace(/\/api\/v1$/, "")
    .replace(/\/v1$/, "");
}

const apiOrigin = normalizeApiOrigin(process.env.NEXT_PUBLIC_API_URL);

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
      {
        source: "/v1/:path*",
        destination: `${apiOrigin}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
