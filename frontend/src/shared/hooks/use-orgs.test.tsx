import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const customInstance = vi.fn().mockResolvedValue([
  { id: "org-live", slug: "live", name: "Live Lab", enabled: true },
  { id: "org-gone", slug: "gone", name: "Closed Lab", enabled: false },
]);
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => customInstance(...args),
}));

import { useOrgName } from "./use-orgs";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

describe("useOrgName", () => {
  it("resolves a disabled org, asking for disabled orgs too", async () => {
    const { result } = renderHook(() => useOrgName(), { wrapper });
    await waitFor(() => expect(result.current("org-gone")).toBe("Closed Lab"));
    expect(customInstance.mock.calls[0][0].params).toEqual({ include_disabled: true });
  });

  it("says when an id is not a known org", async () => {
    const { result } = renderHook(() => useOrgName(), { wrapper });
    await waitFor(() => expect(result.current("org-live")).toBe("Live Lab"));
    expect(result.current("nope")).toBe("Unknown org");
    expect(result.current(null)).toBe("");
  });
});
