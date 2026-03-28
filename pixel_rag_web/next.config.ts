import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/api/media/**",
      },
      {
        protocol: "http",
        hostname: "**",
        port: "8000",
        pathname: "/api/media/**",
      },
    ],
  },
};

export default nextConfig;
