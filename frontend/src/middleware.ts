import { createSentinelAuthzMiddleware } from "@sentinel-auth/nextjs/authz-middleware";

// Server-only env vars — no NEXT_PUBLIC_ prefix (middleware runs at the edge, not in the browser).
const SENTINEL_URL = process.env.SENTINEL_URL ?? "http://localhost:9003";
const IDP_JWKS_URL = process.env.IDP_JWKS_URL ?? "https://www.googleapis.com/oauth2/v3/certs";

export default createSentinelAuthzMiddleware({
  sentinelUrl: SENTINEL_URL,
  idpJwksUrl: IDP_JWKS_URL,
  publicPaths: ["/login", "/auth/callback"],
  loginPath: "/login",
});

export const config = {
  matcher: ["/((?!_next|favicon.ico|public).*)"],
};
