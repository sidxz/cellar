"use client";

import { type ReactNode, createContext, useContext } from "react";

export interface AppConfig {
  apiUrl: string;
  appUrl: string;
  sentinelUrl: string;
  idpProvider: string;
  googleClientId: string;
  entraIdClientId: string;
  entraIdTenantId: string;
}

const defaultConfig: AppConfig = {
  apiUrl: "http://localhost:8000",
  appUrl: "http://localhost:3000",
  sentinelUrl: "http://localhost:9003",
  idpProvider: "google",
  googleClientId: "",
  entraIdClientId: "",
  entraIdTenantId: "",
};

const AppConfigContext = createContext<AppConfig>(defaultConfig);

export function AppConfigProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: ReactNode;
}) {
  return <AppConfigContext.Provider value={config}>{children}</AppConfigContext.Provider>;
}

export function useAppConfig(): AppConfig {
  return useContext(AppConfigContext);
}

/**
 * Fetch runtime config from the server endpoint.
 * Falls back to NEXT_PUBLIC_* env vars for dev without Docker, then to defaults.
 */
export async function fetchAppConfig(): Promise<AppConfig> {
  try {
    const res = await fetch("/api/config");
    if (res.ok) return await res.json();
  } catch {
    // Server not reachable (SSR, tests) — fall through to env vars
  }

  return {
    apiUrl: process.env.NEXT_PUBLIC_API_URL ?? defaultConfig.apiUrl,
    appUrl: process.env.NEXT_PUBLIC_APP_URL ?? defaultConfig.appUrl,
    sentinelUrl: process.env.NEXT_PUBLIC_SENTINEL_URL ?? defaultConfig.sentinelUrl,
    idpProvider: process.env.NEXT_PUBLIC_IDP_PROVIDER ?? defaultConfig.idpProvider,
    googleClientId: process.env.NEXT_PUBLIC_IDP_CLIENT_ID ?? defaultConfig.googleClientId,
    entraIdClientId: process.env.NEXT_PUBLIC_ENTRA_ID_CLIENT_ID ?? defaultConfig.entraIdClientId,
    entraIdTenantId: process.env.NEXT_PUBLIC_ENTRA_TENANT_ID ?? defaultConfig.entraIdTenantId,
  };
}
