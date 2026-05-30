import nextra from "nextra";

const withNextra = nextra({
  // Enable LaTeX-free defaults; we use mermaid + copy-button (built in to theme).
  search: {
    codeblocks: false,
  },
  defaultShowCopyCode: true,
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // RDKit.js touches Node built-ins in its environment-detection path; never
  // bundle it server-side. All chemistry widgets are dynamically imported with
  // ssr:false, but we also harden the webpack config as a belt-and-suspenders.
  webpack(config) {
    config.resolve = config.resolve || {};
    config.resolve.fallback = {
      ...(config.resolve.fallback || {}),
      fs: false,
      path: false,
    };
    return config;
  },
};

export default withNextra(nextConfig);
