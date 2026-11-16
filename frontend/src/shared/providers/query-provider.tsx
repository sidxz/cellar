"use client";

import { getDeleteBlockedError } from "@/shared/hooks/use-admin-delete";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { showError } from "@/shared/lib/toast";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/** A stale edit (409 "StaleEditError": someone saved first) — every caller that can get one
 * explains it in place and offers a reload. */
const isStaleEdit = (error: unknown) =>
  error instanceof ApiError &&
  (error.body as { error?: unknown } | null)?.error === "StaleEditError";

/**
 * Global mutation error handler. A blocked delete (409, "delete_blocked_by_dependencies")
 * is already rendered as a blocker list by its caller (the cascade/admin-delete dialog),
 * and a stale edit by its editor; toasting them here too would just repeat them.
 */
export function onMutationError(error: unknown): void {
  if (getDeleteBlockedError(error) || isStaleEdit(error)) return;
  const message = error instanceof Error ? error.message : "Operation failed";
  showError(message);
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: STALE_TIME.DEFAULT,
            retry: 1,
          },
        },
        mutationCache: new MutationCache({
          onError: onMutationError,
        }),
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
