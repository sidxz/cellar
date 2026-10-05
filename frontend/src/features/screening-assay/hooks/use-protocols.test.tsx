import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useProtocols } from "./use-protocols";

const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const protocol = (id: string) => ({ id, name: `Protocol ${id}` });

describe("useProtocols", () => {
  beforeEach(() => mockCustomInstance.mockReset());

  it("returns every protocol, following the cursor past the first page", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ items: [protocol("a"), protocol("b")], next_cursor: "cur-1" })
      .mockResolvedValueOnce({ items: [protocol("c")], next_cursor: null });

    const { result } = renderHook(() => useProtocols(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((p) => p.id)).toEqual(["a", "b", "c"]);
    expect(mockCustomInstance).toHaveBeenCalledTimes(2);
    expect(mockCustomInstance.mock.calls[1][0].params).toMatchObject({ cursor: "cur-1" });
  });

  it("asks for the largest page the route allows, so one request covers a normal workspace", async () => {
    mockCustomInstance.mockResolvedValueOnce({ items: [protocol("a")], next_cursor: null });

    const { result } = renderHook(() => useProtocols(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCustomInstance.mock.calls[0][0].params).toMatchObject({ limit: 200 });
  });

  it("keeps the project and tag filters on every page it fetches", async () => {
    mockCustomInstance
      .mockResolvedValueOnce({ items: [protocol("a")], next_cursor: "cur-1" })
      .mockResolvedValueOnce({ items: [protocol("b")], next_cursor: null });

    const { result } = renderHook(() => useProtocols("proj-1", { tags: ["t1"], tagLogic: "all" }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    for (const call of mockCustomInstance.mock.calls) {
      expect(call[0].params).toMatchObject({
        project_id: "proj-1",
        tags: ["t1"],
        tag_logic: "all",
      });
    }
  });

  it("stops instead of looping forever when the cursor never clears", async () => {
    mockCustomInstance.mockResolvedValue({ items: [protocol("a")], next_cursor: "always" });

    const { result } = renderHook(() => useProtocols(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockCustomInstance.mock.calls.length).toBeLessThanOrEqual(50);
  });
});
