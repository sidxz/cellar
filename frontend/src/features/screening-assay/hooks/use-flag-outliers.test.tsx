import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn().mockResolvedValue({}),
}));

import { useFlagOutliers } from "./use-flag-outliers";

// Flagging recalculates the run and refits its curves: every view of those values moves.
it("refreshes every cache a recalculation moves", async () => {
  const qc = new QueryClient();
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useFlagOutliers(), { wrapper });
  await act(() =>
    result.current.mutateAsync({ runId: "run-1", well_ids: ["w"], outlier: true, reason: null }),
  );
  const keys = invalidate.mock.calls.map(([arg]) => JSON.stringify(arg?.queryKey));
  for (const key of [
    ["readout-data"],
    ["plate-map"],
    ["dose-response-curves"],
    ["compound-curves"],
    ["multi-compound-curves"],
    ["protocol-activity"],
    ["melting-analysis"],
    ["runs"],
    ["run", "run-1"],
    ["visualization", "dataset"],
  ]) {
    expect(keys).toContain(JSON.stringify(key));
  }
});
