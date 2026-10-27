/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Grounded answers may take longer than Next's default 30-second proxy budget.
  // Backend generation is bounded at 150 seconds, leaving time for retrieval.
  experimental: { proxyTimeout: 210000 },
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/storage/**",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_INTERNAL_URL || "http://localhost:8000"}/api/:path*`,
      },
      {
        source: "/storage/:path*",
        destination: `${process.env.BACKEND_INTERNAL_URL || "http://localhost:8000"}/storage/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
