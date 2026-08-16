"use client";

import { AppSidebar } from "@/shared/components/layout/app-sidebar";
import { Header } from "@/shared/components/layout/header";
import { SidebarInset, SidebarProvider } from "@/shared/components/ui/sidebar";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { usePreferencesSync } from "@/shared/hooks/use-preferences-sync";
import { useAuthz } from "@duar-auth/nextjs";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

function DashboardSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-md space-y-4 px-4">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { authState, isLoading } = useAuthz();
  const router = useRouter();
  usePreferencesSync();

  useEffect(() => {
    // Only bounce to login when the session is truly gone. During `needs_reauth`
    // (IdP token lost on reload) the AuthzProvider's `autoReauth` performs a
    // silent re-auth redirect — sending to /login here would pre-empt it.
    if (!isLoading && authState === "unauthenticated") {
      router.replace("/login");
    }
  }, [isLoading, authState, router]);

  if (isLoading || authState !== "authenticated") {
    return <DashboardSkeleton />;
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <Header />
        <main className="flex-1 overflow-auto p-4">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
