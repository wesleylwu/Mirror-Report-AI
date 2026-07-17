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
        {
          source: "/api/generate_excel",
          destination: "/api/py_generate_excel",
        },
        {
          source: "/api/save_edits",
          destination: "/api/py_save_edits",
        },
      ];
    } else {
      return [
        {
          source: "/api/convert",
          destination: "/api/convert_local",
        },
      ];
    }
  },
};

export default nextConfig;
