import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useProtocolPlateQcAverages } from "./use-protocol-stats";
import { useImportRunFile } from "./use-run-import";
import { useRecomputeRun } from "./use-runs";

const averages = (n: number) => ({
  averages: [{ readout_definition_id: "rd1", layer: "raw", z_prime: { mean: 0.8, sd: 0.1, n } }],
});

/** The app's client: data stays fresh for a minute, so only an invalidation refetches. */
function setup() {
  let plates = 2;
  vi.mocked(customInstance).mockReset();
  vi.mocked(customInstance).mockImplementation(async (config) => {
    const { url } = config as { url: string };
    if (url.endsWith("/plate-qc-averages")) return averages(plates);
    plates = 3; // the import / recompute stored this run's plate QC
    return { fit_warnings: [], computed_readouts: 1 };
  });
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    () => ({
      averages: useProtocolPlateQcAverages("p1"),
      importFile: useImportRunFile("r1"),
      recompute: useRecomputeRun(),
    }),
    { wrapper },
  );
}

const plateCount = (r: ReturnType<typeof setup>["result"]) =>
  r.current.averages.data?.averages[0].z_prime?.n;

describe("protocol plate-QC averages", () => {
  it("count the plates of a run imported while the page is open", async () => {
    const { result } = setup();
    await waitFor(() => expect(plateCount(result)).toBe(2));

    await act(() =>
      result.current.importFile.mutateAsync({
        preview_id: "pv",
        mapping: { well: "Well", readout_columns: [] },
        file: new File(["x"], "run.csv"),
      } as Parameters<typeof result.current.importFile.mutateAsync>[0]),
    );

    await waitFor(() => expect(plateCount(result)).toBe(3));
  });

  it("follow a recompute of a run", async () => {
    const { result } = setup();
    await waitFor(() => expect(plateCount(result)).toBe(2));

    await act(() => result.current.recompute.mutateAsync({ runId: "r1" }));

    await waitFor(() => expect(plateCount(result)).toBe(3));
  });
});
