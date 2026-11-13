import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
  showWarning: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useImportInstrumentFile } from "./use-instrument-import";
import { useRelabelPositions } from "./use-relabel-positions";
import { useResetRunData } from "./use-run-import";
import { useRecomputeRun } from "./use-runs";

const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const keys = () => invalidate.mock.calls.map(([arg]) => JSON.stringify(arg?.queryKey));
  return { wrapper, keys };
}

// Every mutation that changes a run's steps, roles or computed values must refresh the
// melting-steps panel, or it keeps showing the analysis it loaded first.
describe("run data mutations refresh the melting analysis", () => {
  beforeEach(() => mockCustomInstance.mockReset().mockResolvedValue({ computed_readouts: 0 }));

  const melting = JSON.stringify(["melting-analysis", "run-1"]);

  it("relabeling positions", async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useRelabelPositions("run-1"), { wrapper });
    await act(() => result.current.mutateAsync({ positions: [] } as never));
    expect(keys()).toContain(melting);
  });

  it("recompute", async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useRecomputeRun(), { wrapper });
    await act(() => result.current.mutateAsync({ runId: "run-1" }));
    expect(keys()).toContain(JSON.stringify(["melting-analysis"]));
  });

  it("instrument import", async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useImportInstrumentFile("run-1"), { wrapper });
    await act(() =>
      result.current.mutateAsync({ file: new File(["x"], "f.xlsx"), labelling: {} as never }),
    );
    expect(keys()).toContain(melting);
  });

  it("reset run data, which also deletes the traces", async () => {
    const { wrapper, keys } = setup();
    const { result } = renderHook(() => useResetRunData("run-1"), { wrapper });
    await act(() => result.current.mutateAsync());
    expect(keys()).toContain(melting);
    expect(keys()).toContain(JSON.stringify(["measured-curves"]));
  });
});
