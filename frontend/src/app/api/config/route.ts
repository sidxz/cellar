/**
 * Runtime configuration endpoint.
 *
 * Reads environment variables at request time (NOT build time), enabling
 * a single universal Docker image that works across environments.
 *
 * Variables use APP_ prefix (server-side only) instead of NEXT_PUBLIC_
 * (which gets baked into the JS bundle at build time).
 */
export function GET() {
  return Response.json({
    apiUrl: process.env.APP_API_URL ?? "http://localhost:8000",
    appUrl: process.env.APP_URL ?? "http://localhost:3000",
    sentinelUrl: process.env.APP_SENTINEL_URL ?? "http://localhost:9003",
    idpProvider: process.env.APP_IDP_PROVIDER ?? "google",
    googleClientId: process.env.APP_GOOGLE_CLIENT_ID ?? "",
    entraIdClientId: process.env.APP_ENTRA_ID_CLIENT_ID ?? "",
    entraIdTenantId: process.env.APP_ENTRA_ID_TENANT_ID ?? "",
  });
}
