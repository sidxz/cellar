"use client";

import { getDeleteBlockedError } from "@/shared/hooks/use-admin-delete";
import { isStaleEdit } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import { showError } from "@/shared/lib/toast";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/**
 * Global mutation error handler. A blocked delete (409, "delete_blocked_by_dependencies")
 * is already rendered as a blocker list by its caller (the cascade/admin-delete dialog),
 * and a stale edit by its editor (a race 409 too, for a mutation whose `meta.raceIsStale`
 * says it explains one); toasting them here too would just repeat them.
 */
export function onMutationError(
  error: unknown,
  _variables?: unknown,
  _onMutateResult?: unknown,
  mutation?: { meta?: Record<string, unknown> },
): void {
  const race = mutation?.meta?.raceIsStale === true;
  if (getDeleteBlockedError(error) || isStaleEdit(error, { race })) return;
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
