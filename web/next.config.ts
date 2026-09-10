import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/app/graph",
        destination: "/app/audit",
        permanent: false,
      },
      {
        source: "/app/matrix",
        destination: "/app/audit",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
