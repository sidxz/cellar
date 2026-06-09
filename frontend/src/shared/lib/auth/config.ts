import type { AppConfig } from "@/shared/lib/app-config";
import {
  AuthzLocalStorageStore,
  type IdpConfig,
  IdpConfigs,
  SentinelAuthz,
} from "@sentinel-auth/js";

function buildIdps(config: AppConfig): Record<string, IdpConfig> {
  const idps: Record<string, IdpConfig> = {};
  if (config.googleClientId) {
    idps.google = IdpConfigs.google(config.googleClientId);
  }
  if (config.entraIdClientId && config.entraIdTenantId) {
    idps.entraId = IdpConfigs.entraId(config.entraIdClientId, config.entraIdTenantId);
  }
  return idps;
}

let _client: SentinelAuthz | null = null;

/**
 * Create (or return cached) SentinelAuthz client.
 * Accepts runtime AppConfig so no process.env is read at module load.
 */
export function getSentinelClient(config?: AppConfig): SentinelAuthz {
  if (!_client) {
    const sentinelUrl = config?.sentinelUrl ?? "http://localhost:9003";
    const appUrl = config?.appUrl ?? "http://localhost:3000";

    _client = new SentinelAuthz({
      sentinelUrl,
      idps: config ? buildIdps(config) : {},
      redirectUri: `${appUrl}/auth/callback`,
      // Required since Sentinel 0.11.0: the browser no longer mints authz tokens
      // directly. It POSTs to this same-origin backend route, which forwards to
      // Sentinel's /authz/resolve with the service key. See app/api/auth/mint.
      mintEndpoint: "/api/auth/mint",
      storage: typeof window !== "undefined" ? new AuthzLocalStorageStore() : undefined,
      autoRefresh: true,
      refreshBuffer: 30,
    });
  }
  return _client;
}
