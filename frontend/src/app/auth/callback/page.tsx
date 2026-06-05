"use client";

import { CHEM_ITEMS } from "@/shared/components/backgrounds/chem-items";
import { GridMotion } from "@/shared/components/backgrounds/grid-motion";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { AuthzCallback } from "@sentinel-auth/nextjs";
import { useRouter } from "next/navigation";

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
          <h1 className="text-lg font-semibold tracking-tight">Cellar</h1>
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
                onSuccess={() => router.replace("/")}
                onError={(error) =>
                  router.replace(`/login?error=${encodeURIComponent(error.message)}`)
                }
                loadingComponent={
                  <div>
                    <h2 className="text-sm font-medium text-muted-foreground">Signing in...</h2>
                    <div className="mt-4 space-y-3">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-4 w-3/4" />
                    </div>
                  </div>
                }
                workspaceSelector={({ workspaces, onSelect, isLoading: selecting }) => (
                  <div>
                    <h2 className="text-sm font-medium text-muted-foreground">
                      Select workspace to continue
                    </h2>
                    <div className="mt-4 space-y-2">
                      {workspaces.map((ws) => (
                        <Button
                          key={ws.id}
                          variant="outline"
                          className="w-full justify-start rounded-[11px]"
                          disabled={selecting}
                          onClick={() => onSelect(ws.id)}
                        >
                          <span className="truncate">{ws.name}</span>
                          <span className="ml-auto text-xs text-muted-foreground">{ws.role}</span>
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
