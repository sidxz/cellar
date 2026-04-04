"use client";

import { getSentinelClient } from "@/shared/lib/auth/config";
import { AuthzProvider } from "@sentinel-auth/nextjs";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  return <AuthzProvider client={getSentinelClient()}>{children}</AuthzProvider>;
}
