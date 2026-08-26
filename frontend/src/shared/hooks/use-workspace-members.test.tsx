import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useMemberNames } from "./use-workspace-members";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
const mocked = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useMemberNames", () => {
  it("resolves ids to names over the full member list, with fallbacks", async () => {
    mocked.mockResolvedValue([
      { user_id: "u1", name: "Maia Young", email: "m@x", avatar_url: null, role: "editor" },
    ]);
    const { result } = renderHook(() => useMemberNames(), { wrapper });
    expect(result.current("u1")).toBe("…"); // still loading
    await waitFor(() => expect(result.current("u1")).toBe("Maia Young"));
    expect(result.current("nope")).toBe("Unknown member");
    expect(result.current(null)).toBe("");
    expect(result.current(undefined)).toBe("");
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ url: "/api/v1/user/workspace-members", params: undefined }),
    );
  });
});
