import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { ApiError, customInstance } from "@/shared/lib/api/custom-instance";
import { PreviewExpiredError, useImportRunFile, useRepreviewRunFile } from "./use-run-import";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

const FILE = new File(["Well,Raw\nA1,0.5\n"], "run.csv", { type: "text/csv" });
const MAPPING = {
  well: "Well",
  readout_columns: [{ header: "Raw", readout_definition_id: "rd-1" }],
};
const GONE = new ApiError("API error: 404", 404, {
  error: "NotFoundError",
  message: "Preview 'pv-old' not found",
});

type Call = { url: string; data?: unknown };
const calls = () => vi.mocked(customInstance).mock.calls.map(([c]) => c as Call);

beforeEach(() => vi.mocked(customInstance).mockReset());

describe("a preview the server no longer holds", () => {
  it("is uploaded again and re-previewed with the chemist's mapping", async () => {
    vi.mocked(customInstance)
      .mockRejectedValueOnce(GONE)
      .mockResolvedValueOnce({ preview_id: "pv-new" })
      .mockResolvedValueOnce({ preview_id: "pv-new", headers: ["Well", "Raw"] });
    const { result } = renderHook(() => useRepreviewRunFile("run-1"), { wrapper });

    const data = await act(() =>
      result.current.mutateAsync({ preview_id: "pv-old", mapping: MAPPING, file: FILE }),
    );

    expect(data).toMatchObject({ preview_id: "pv-new" });
    const [first, upload, retry] = calls();
    expect(first.data).toEqual({ preview_id: "pv-old", mapping: MAPPING });
    expect(upload.url).toMatch(/\/runs\/run-1\/preview-file$/);
    expect((upload.data as FormData).get("file")).toBe(FILE);
    expect(retry).toMatchObject({
      url: expect.stringMatching(/\/runs\/run-1\/repreview-file$/),
      data: { preview_id: "pv-new", mapping: MAPPING },
    });
  });

  it("fails as expired when the upload fails too", async () => {
    vi.mocked(customInstance)
      .mockRejectedValueOnce(GONE)
      .mockRejectedValueOnce(new ApiError("API error: 500", 500, undefined));
    const { result } = renderHook(() => useRepreviewRunFile("run-1"), { wrapper });

    const error = await act(() =>
      result.current
        .mutateAsync({ preview_id: "pv-old", mapping: MAPPING, file: FILE })
        .catch((e: unknown) => e),
    );

    expect(error).toBeInstanceOf(PreviewExpiredError);
  });

  it("is uploaded again before an import, keeping the batch picks", async () => {
    vi.mocked(customInstance)
      .mockRejectedValueOnce(GONE)
      .mockResolvedValueOnce({ preview_id: "pv-new" })
      .mockResolvedValueOnce({ wells_created: 1, values_inserted: 1 });
    const { result } = renderHook(() => useImportRunFile("run-1"), { wrapper });
    const picks = [{ molecule_id: "m-1", batch_id: "b-1" }];

    await act(() =>
      result.current.mutateAsync({
        preview_id: "pv-old",
        mapping: MAPPING,
        compound_batch_overrides: picks,
        file: FILE,
      }),
    );

    expect(calls()[2]).toMatchObject({
      url: expect.stringMatching(/\/runs\/run-1\/import-file$/),
      data: { preview_id: "pv-new", mapping: MAPPING, compound_batch_overrides: picks },
    });
  });

  it("is not confused with any other 404", async () => {
    const runGone = new ApiError("API error: 404", 404, {
      error: "NotFoundError",
      message: "Run 'run-1' not found",
    });
    vi.mocked(customInstance).mockRejectedValueOnce(runGone);
    const { result } = renderHook(() => useRepreviewRunFile("run-1"), { wrapper });

    const error = await act(() =>
      result.current
        .mutateAsync({ preview_id: "pv-old", mapping: MAPPING, file: FILE })
        .catch((e: unknown) => e),
    );

    expect(error).toBe(runGone);
    expect(calls()).toHaveLength(1);
  });
});
