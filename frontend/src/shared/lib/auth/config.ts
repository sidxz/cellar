import {
  AuthzLocalStorageStore,
  type IdpConfig,
  IdpConfigs,
  SentinelAuthz,
  type SentinelAuthzConfig,
} from "@sentinel-auth/js";

const IDP_PROVIDER = process.env.NEXT_PUBLIC_IDP_PROVIDER ?? "google";
const IDP_CLIENT_ID = process.env.NEXT_PUBLIC_IDP_CLIENT_ID ?? "";
const SENTINEL_URL = process.env.NEXT_PUBLIC_SENTINEL_URL ?? "http://localhost:9003";
const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

function buildIdpConfig(provider: string, clientId: string): Record<string, IdpConfig> {
  switch (provider) {
    case "google":
      return { google: IdpConfigs.google(clientId) };
    case "entraId":
      return {
        entraId: IdpConfigs.entraId(clientId, process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? ""),
      };
    default:
      return { [provider]: IdpConfigs.google(clientId) };
  }
}

export const sentinelConfig: SentinelAuthzConfig = {
  sentinelUrl: SENTINEL_URL,
  idps: buildIdpConfig(IDP_PROVIDER, IDP_CLIENT_ID),
  redirectUri: `${APP_URL}/auth/callback`,
  storage: typeof window !== "undefined" ? new AuthzLocalStorageStore() : undefined,
  autoRefresh: true,
  refreshBuffer: 30,
};

export const defaultIdpProvider = IDP_PROVIDER;

/** Shared SentinelAuthz client singleton — used by AuthzProvider and API custom-instance. */
let _sentinelClient: SentinelAuthz | null = null;

export function getSentinelClient(): SentinelAuthz {
  if (!_sentinelClient) {
    _sentinelClient = new SentinelAuthz(sentinelConfig);
  }
  return _sentinelClient;
}
