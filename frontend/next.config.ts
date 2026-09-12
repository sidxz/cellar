import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // @structflo/components ships raw .tsx with no build step — Next compiles it.
  transpilePackages: ["@structflo/components"],
  turbopack: {
    resolveAlias: {
      // RDKit.js WASM has `require('fs')` in its Node.js detection path.
      // Stub it out for client bundles — the WASM loader uses fetch, not fs.
      fs: "./src/shared/lib/rdkit/empty-module.ts",
    },
  },
};

export default nextConfig;
