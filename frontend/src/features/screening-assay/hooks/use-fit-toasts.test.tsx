import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showWarning: vi.fn(),
  showInfo: vi.fn(),
  showError: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showInfo, showSuccess, showWarning } from "@/shared/lib/toast";
import { useImportRunFile } from "./use-run-import";
import { useRecomputeRun } from "./use-runs";

const NOTE = "91 compounds tested at fewer than 4 doses — no curve";
const FAILED = "CC-061391 (SACC-0108241) on 'IC50': fit failed — did not converge";

function setup(response: object) {
  vi.mocked(customInstance).mockResolvedValue(response);
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => ({ recompute: useRecomputeRun(), importFile: useImportRunFile("r1") }), {
    wrapper,
  }).result;
}

beforeEach(() => vi.clearAllMocks());

describe("refit messages", () => {
  it("a recompute names compounds tested at too few doses as a neutral note, not a fit issue", async () => {
    const result = setup({ computed_readouts: 182, fit_warnings: [], fit_notes: [NOTE] });

    await act(() => result.current.recompute.mutateAsync({ runId: "r1" }));

    expect(showSuccess).toHaveBeenCalledWith(expect.stringContaining("182"), {
      description: NOTE,
    });
    expect(showWarning).not.toHaveBeenCalled();
  });

  it("a recompute warns of fits that failed, by compound", async () => {
    const result = setup({ computed_readouts: 182, fit_warnings: [FAILED], fit_notes: [] });

    await act(() => result.current.recompute.mutateAsync({ runId: "r1" }));

    expect(showWarning).toHaveBeenCalledWith(expect.stringContaining("1"), {
      description: FAILED,
    });
  });

  it("an import says the same", async () => {
    const result = setup({ fit_warnings: [], fit_notes: [NOTE] });

    await act(() =>
      result.current.importFile.mutateAsync({
        preview_id: "pv",
        mapping: { well: "Well", readout_columns: [] },
        file: new File(["x"], "run.csv"),
      } as Parameters<typeof result.current.importFile.mutateAsync>[0]),
    );

    expect(showInfo).toHaveBeenCalledWith(NOTE);
    expect(showWarning).not.toHaveBeenCalled();
  });
});
