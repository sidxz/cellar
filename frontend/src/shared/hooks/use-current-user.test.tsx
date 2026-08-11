import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: vi.fn().mockResolvedValue({
    user_id: "u1",
    email: "chemist@abbvie.com",
    name: "Chemist",
    org_id: "org1",
    org_slug: "abbvie",
  }),
}));

import { useCurrentUser } from "./use-current-user";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useCurrentUser", () => {
  it("fetches the current user", async () => {
    const { result } = renderHook(() => useCurrentUser(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      user_id: "u1",
      email: "chemist@abbvie.com",
      name: "Chemist",
      org_id: "org1",
      org_slug: "abbvie",
    });
  });
});
