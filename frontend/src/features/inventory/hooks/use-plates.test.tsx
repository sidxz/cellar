import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const customInstance = vi.fn(async (_args: unknown) => []);
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/features/chemical-registration", () => ({ MOLECULES_KEY: ["molecules"] }));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { usePlates } from "./use-plates";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("usePlates", () => {
  beforeEach(() => vi.clearAllMocks());

  it("forwards owner_org_id when provided", async () => {
    renderHook(() => usePlates({ owner_org_id: "org-1", status: "stored" }), { wrapper });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params).toEqual({ owner_org_id: "org-1", status: "stored" });
  });

  it("omits owner_org_id when not provided", async () => {
    renderHook(() => usePlates({ status: "stored" }), { wrapper });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params).toEqual({ status: "stored" });
  });

  it("does not fetch when enabled is false", () => {
    renderHook(() => usePlates({ owner_org_id: "org-1" }, { enabled: false }), { wrapper });
    expect(customInstance).not.toHaveBeenCalled();
  });
});
