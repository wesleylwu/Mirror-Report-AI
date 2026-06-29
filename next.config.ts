import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["172.16.0.126"],
  typedRoutes: false,
  async rewrites() {
    if (process.env.VERCEL) {
      return [
        {
          source: "/api/convert",
          destination: "/api/py_convert",
        },
      ];
    }
    return [];
  },
};

export default nextConfig;
