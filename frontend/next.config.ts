import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  async rewrites() {
    return ['account', 'market', 'trade-bot', 'pnl-hedge', 'agents'].map((section) => ({
      source: `/${section}`,
      destination: '/',
    }))
  },
};

export default nextConfig;
