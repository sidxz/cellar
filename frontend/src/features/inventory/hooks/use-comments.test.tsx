import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const customInstance = vi.fn(async (_args: unknown) => []);
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { useAddComment, useComments } from "./use-comments";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useComments", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs /api/v1/comments with target_type/target_id params for a target scope", async () => {
    const { result } = renderHook(
      () => useComments({ targetType: "plate_group", targetId: "g1" }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const arg = customInstance.mock.calls[0][0] as {
      url: string;
      method: string;
      params?: Record<string, string>;
    };
    expect(arg.url).toBe("/api/v1/comments");
    expect(arg.method).toBe("GET");
    expect(arg.params).toEqual({ target_type: "plate_group", target_id: "g1" });
  });

  it("GETs /api/v1/comments with a loan_id param for a loan scope", async () => {
    const { result } = renderHook(() => useComments({ loanId: "l1" }), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const arg = customInstance.mock.calls[0][0] as {
      url: string;
      method: string;
      params?: Record<string, string>;
    };
    expect(arg.url).toBe("/api/v1/comments");
    expect(arg.method).toBe("GET");
    expect(arg.params).toEqual({ loan_id: "l1" });
  });
});

describe("useAddComment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POSTs the comment body to /api/v1/comments", async () => {
    const { result } = renderHook(() => useAddComment(), { wrapper });
    act(() => {
      result.current.mutate({ target_type: "plate", target_id: "p1", body: "x" });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const arg = customInstance.mock.calls[0][0] as {
      url: string;
      method: string;
      data?: Record<string, unknown>;
    };
    expect(arg.url).toBe("/api/v1/comments");
    expect(arg.method).toBe("POST");
    expect(arg.data).toEqual({ target_type: "plate", target_id: "p1", body: "x" });
  });
});
