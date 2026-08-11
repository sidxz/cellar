import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCreatePlateGroup, usePlateGroupTree } from "./use-plate-groups";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("usePlateGroupTree", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches the tree for an org", async () => {
    mocked.mockResolvedValueOnce({ org_id: "o1", roots: [] });
    const { result } = renderHook(() => usePlateGroupTree("o1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-groups/tree",
        method: "GET",
        params: { org_id: "o1" },
      }),
    );
    expect(result.current.data?.org_id).toBe("o1");
  });

  it("omits org_id param when not given (server defaults to my org)", async () => {
    mocked.mockResolvedValueOnce({ org_id: "mine", roots: [] });
    const { result } = renderHook(() => usePlateGroupTree(undefined), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(expect.objectContaining({ params: {} }));
  });

  it("respects enabled=false", () => {
    renderHook(() => usePlateGroupTree("o1", { enabled: false }), { wrapper });
    expect(mocked).not.toHaveBeenCalled();
  });
});

describe("useCreatePlateGroup", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs and resolves", async () => {
    mocked.mockResolvedValueOnce({ id: "g1", name: "G" });
    const { result } = renderHook(() => useCreatePlateGroup(), { wrapper });
    result.current.mutate({ name: "G" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-groups",
        method: "POST",
        data: { name: "G" },
      }),
    );
  });
});
