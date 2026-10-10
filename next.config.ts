import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  ...(process.env.NODE_ENV === "production" ? { output: "export" as const } : {}),
  allowedDevOrigins: ["127.0.0.1"],
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  basePath,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
