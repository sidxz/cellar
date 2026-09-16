import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/admin/admin", () => ({
  cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost: vi.fn(),
}));

import { cascadePreviewApiV1AdminEntityTypeEntityIdCascadePreviewPost as mockApi } from "@/shared/lib/api/admin/admin";
import { useCascadePreview } from "./use-cascade-preview";

const mockPreview = mockApi as ReturnType<typeof vi.fn>;

function makeWrapper() {
  // Mirrors the app's QueryProvider default staleTime (60s, see query-defaults.ts) —
  // a stale-time-naive reopen would otherwise serve cached data instead of refetching.
  const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useCascadePreview", () => {
  beforeEach(() => {
    mockPreview.mockReset();
    mockPreview.mockResolvedValue({ blockers: [], warnings: [] });
  });

  it("refetches on reopen instead of serving a preview cached under the global staleTime", async () => {
    const wrapper = makeWrapper();
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useCascadePreview("run", "r-1", enabled),
      { wrapper, initialProps: { enabled: true } },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPreview).toHaveBeenCalledTimes(1);

    rerender({ enabled: false }); // dialog closes
    rerender({ enabled: true }); // dialog reopens, still within the 60s staleTime

    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
  });
});
