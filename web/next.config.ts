import type { NextConfig } from "next";

// Prod varsayılanı: Render üzerindeki FastAPI. Yerel geliştirmede
// web/.env.local içinde API_BACKEND_URL=http://localhost:8000 olarak ezilebilir.
const API_BACKEND =
  process.env.API_BACKEND_URL || "https://momenz.onrender.com";

const nextConfig: NextConfig = {
  // API'yi aynı origin'e proxy'leriz: cookie'ler first-party kalır,
  // <img src="/api/v1/images/..."> isteklerine oturum cookie'si gider.
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_BACKEND}/api/v1/:path*`,
      },
    ];
  },
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
