"use client";

import { CHEM_ITEMS } from "@/shared/components/backgrounds/chem-items";
import { GridMotion } from "@/shared/components/backgrounds/grid-motion";
import { HexLensLogo } from "@/shared/components/hex-lens-logo";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { AuthzCallback } from "@sentinel-auth/nextjs";
import { useRouter } from "next/navigation";
import { WorkspaceSelector } from "./workspace-selector";

export default function CallbackPage() {
  const router = useRouter();

  return (
    <div className="fixed inset-0 overflow-hidden bg-background">
      {/* ── Left: animated background only ── */}
      <div className="absolute inset-0 md:right-[460px]">
        <GridMotion items={CHEM_ITEMS} />
      </div>

      {/* ── Right: branding + callback ── */}
      <div className="relative z-20 flex min-h-screen flex-col md:ml-auto md:w-[460px] md:border-l md:border-sidebar-border md:bg-sidebar">
        {/* Top-right branding */}
        <div
          className="flex flex-col items-end px-8 pt-8"
          style={{ animation: "auth-enter 0.7s ease-out 0.1s both" }}
        >
          <div className="flex items-center gap-3">
            <HexLensLogo className="size-12" />
            <h1
              className="text-3xl font-medium tracking-tight"
              style={{ fontFamily: "var(--font-overused-grotesk), ui-sans-serif, sans-serif" }}
            >
              ChemCellar
            </h1>
          </div>
          <a
            href="https://www.chemcellar.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            www.chemcellar.com
          </a>
        </div>

        {/* Centered callback content */}
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="w-full max-w-[320px] px-6 md:px-0">
            <div style={{ animation: "auth-enter 0.7s ease-out 0.2s both" }}>
              <AuthzCallback
                onSuccess={(_user, returnTo) => router.replace(returnTo ?? "/")}
                onError={(error) =>
                  router.replace(`/login?error=${encodeURIComponent(error.message)}`)
                }
                onSilentReauthFailed={() => router.replace("/login")}
                loadingComponent={
                  <div>
                    <h2 className="text-sm font-medium text-muted-foreground">Signing in...</h2>
                    <div className="mt-4 space-y-3">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-4 w-3/4" />
                    </div>
                  </div>
                }
                workspaceSelector={(props) => <WorkspaceSelector {...props} />}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
