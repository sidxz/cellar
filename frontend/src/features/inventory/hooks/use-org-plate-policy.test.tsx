import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const policy = {
  org_id: "org1",
  require_approval: true,
  confirmation: "kiosk_scan",
  default_due_days: 14,
  version: 1,
};

const customInstance = vi.fn(async (_args: unknown) => policy);
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { useOrgPlatePolicy, useSetOrgPlatePolicy } from "./use-org-plate-policy";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useOrgPlatePolicy", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches the policy for the given org", async () => {
    const { result } = renderHook(() => useOrgPlatePolicy("org1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(policy);
    const arg = customInstance.mock.calls[0][0] as { url: string; method: string };
    expect(arg.url).toBe("/api/v1/org-plate-policies/org1");
    expect(arg.method).toBe("GET");
  });

  it("does not fetch when orgId is undefined", () => {
    renderHook(() => useOrgPlatePolicy(undefined), { wrapper });
    expect(customInstance).not.toHaveBeenCalled();
  });
});

describe("useSetOrgPlatePolicy", () => {
  beforeEach(() => vi.clearAllMocks());

  it("PUTs the policy body to the org's endpoint", async () => {
    const { result } = renderHook(() => useSetOrgPlatePolicy("org1"), { wrapper });
    act(() => {
      result.current.mutate({
        require_approval: true,
        confirmation: "admin_confirm",
        default_due_days: null,
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const arg = customInstance.mock.calls[0][0] as {
      url: string;
      method: string;
      data?: Record<string, unknown>;
    };
    expect(arg.url).toBe("/api/v1/org-plate-policies/org1");
    expect(arg.method).toBe("PUT");
    expect(arg.data).toEqual({
      require_approval: true,
      confirmation: "admin_confirm",
      default_due_days: null,
    });
  });
});
