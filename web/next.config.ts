import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone keeps the production image small: Next copies only the files
  // the server actually needs instead of the whole node_modules tree.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
