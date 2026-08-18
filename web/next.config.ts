import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 議席計算はすべてブラウザ内で完結するのでサーバーは要らない。
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
