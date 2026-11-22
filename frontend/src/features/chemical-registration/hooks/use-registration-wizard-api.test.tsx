import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const customInstance = vi.fn().mockResolvedValue({ workflow_id: "w-1", status: "pending" });
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => customInstance(...args),
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import {
  usePreviewBulkRegistration,
  useStartBulkRegistration,
  useSuggestColumnMapping,
} from "./use-registration-wizard-api";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useStartBulkRegistration", () => {
  it("sends one project_ids form field per chosen project", async () => {
    const { result } = renderHook(() => useStartBulkRegistration(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        file: new File(["name,smiles\n"], "rows.csv"),
        file_format: "csv",
        project_ids: ["p-1", "p-2"],
      }),
    );
    const form = customInstance.mock.calls[0][0].data as FormData;
    expect(form.getAll("project_ids")).toEqual(["p-1", "p-2"]);
  });
});

describe("useStartBulkRegistration — who disclosed the structures", () => {
  it("a changed discloser is sent as disclosed_by and disclosed_by_org_id", async () => {
    customInstance.mockClear();
    const { result } = renderHook(() => useStartBulkRegistration(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        file: new File(["name,smiles\n"], "rows.csv"),
        file_format: "csv",
        disclosed_by: "u-jane",
        disclosed_by_org_id: "org-partner",
      }),
    );
    const form = customInstance.mock.calls[0][0].data as FormData;
    expect([form.get("disclosed_by"), form.get("disclosed_by_org_id")]).toEqual([
      "u-jane",
      "org-partner",
    ]);
    expect(form.has("originating_org_id")).toBe(false);
  });

  it("defaults send neither field", async () => {
    customInstance.mockClear();
    const { result } = renderHook(() => useStartBulkRegistration(), { wrapper });
    await act(() =>
      result.current.mutateAsync({ file: new File(["x"], "rows.csv"), file_format: "csv" }),
    );
    const form = customInstance.mock.calls[0][0].data as FormData;
    expect(form.has("disclosed_by") || form.has("disclosed_by_org_id")).toBe(false);
  });
});

describe("usePreviewBulkRegistration", () => {
  it("sends the column mapping as JSON next to the file, and no field without one", async () => {
    customInstance.mockClear();
    const { result } = renderHook(() => usePreviewBulkRegistration(), { wrapper });
    const file = new File(["Molecule Name\n"], "rows.csv");
    const mapping = { columns: [{ header: "Molecule Name", target: "name" as const }] };
    await act(() => result.current.mutateAsync({ file, mapping }));
    await act(() => result.current.mutateAsync({ file, mapping: null }));

    const [withMapping, without] = customInstance.mock.calls.map((c) => c[0]);
    expect(withMapping.url).toBe("/api/v1/bulk-registrations/preview");
    expect((withMapping.data as FormData).get("file")).toBeInstanceOf(File);
    expect(JSON.parse((withMapping.data as FormData).get("column_mapping") as string)).toEqual(
      mapping,
    );
    expect((without.data as FormData).has("column_mapping")).toBe(false);
  });
});

describe("useStartBulkRegistration column mapping", () => {
  it("passes the mapping through as the column_mapping form field", async () => {
    customInstance.mockClear();
    const { result } = renderHook(() => useStartBulkRegistration(), { wrapper });
    const mapping = JSON.stringify({ columns: [{ header: "SMILES", target: "smiles" }] });
    await act(() =>
      result.current.mutateAsync({
        file: new File(["SMILES\n"], "rows.csv"),
        file_format: "csv",
        column_mapping: mapping,
      }),
    );
    expect((customInstance.mock.calls[0][0].data as FormData).get("column_mapping")).toBe(mapping);
  });
});

describe("useSuggestColumnMapping", () => {
  it("posts the headers to the suggestion endpoint", async () => {
    customInstance.mockClear();
    const { result } = renderHook(() => useSuggestColumnMapping(), { wrapper });
    await act(() => result.current.mutateAsync(["Molecule Name", "SMILES"]));
    expect(customInstance.mock.calls[0][0]).toMatchObject({
      url: "/api/v1/bulk-registrations/suggest-mapping",
      method: "POST",
      data: { headers: ["Molecule Name", "SMILES"] },
    });
  });
});
