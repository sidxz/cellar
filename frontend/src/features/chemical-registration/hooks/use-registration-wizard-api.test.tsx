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

import { useStartBulkRegistration } from "./use-registration-wizard-api";

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
        originating_org_id: "org-1",
        project_ids: ["p-1", "p-2"],
      }),
    );
    const form = customInstance.mock.calls[0][0].data as FormData;
    expect(form.getAll("project_ids")).toEqual(["p-1", "p-2"]);
  });
});
