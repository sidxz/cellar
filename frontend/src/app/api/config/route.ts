/**
 * Runtime configuration endpoint.
 *
 * Reads environment variables at request time (NOT build time) for
 * environment-specific values, enabling a single universal Docker image.
 *
 * The UI build identity (uiVersion/uiGitSha/uiBuildDate) is image-specific,
 * baked into the image at build time via APP_VERSION/APP_GIT_SHA/APP_BUILD_DATE
 * (see frontend/Dockerfile + publish-images.yml). It is delivered here so the
 * client has a single config-fetch mechanism.
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
    // Build identity (image-specific) + runtime environment (env-specific).
    uiVersion: process.env.APP_VERSION || "0.0.0+dev",
    uiGitSha: process.env.APP_GIT_SHA || "unknown",
    uiBuildDate: process.env.APP_BUILD_DATE || "unknown",
    environment: process.env.APP_ENV || "development",
  });
}
