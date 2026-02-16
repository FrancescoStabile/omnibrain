import type { NextConfig } from "next";

const API_PORT = process.env.OMNIBRAIN_API_PORT || "7432";
const API_HOST = process.env.OMNIBRAIN_API_HOST || "127.0.0.1";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://${API_HOST}:${API_PORT}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
