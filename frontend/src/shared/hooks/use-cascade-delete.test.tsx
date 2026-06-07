import { ApiError } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/admin/admin", () => ({
  cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete } from "@/shared/lib/api/admin/admin";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useCascadeDelete } from "./use-cascade-delete";

const mockCascade = cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete as ReturnType<
  typeof vi.fn
>;
const mockShowError = showError as ReturnType<typeof vi.fn>;
const mockShowSuccess = showSuccess as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { wrapper, invalidateSpy };
}

describe("useCascadeDelete", () => {
  beforeEach(() => {
    mockCascade.mockReset();
    mockShowError.mockReset();
    mockShowSuccess.mockReset();
  });

  it("toasts success and invalidates on a clean cascade delete", async () => {
    mockCascade.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCascadeDelete({ onSuccess }), { wrapper });

    result.current.mutate({
      entityType: "protocol",
      entityId: "p-1",
      typedName: "My Protocol",
      reason: "cleanup",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalled();
    expect(mockShowSuccess).toHaveBeenCalledWith("Deleted");
    expect(onSuccess).toHaveBeenCalled();
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it("toasts the typed error message on failure", async () => {
    mockCascade.mockRejectedValue(new ApiError("API error: 409 — name mismatch", 409, undefined));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useCascadeDelete(), { wrapper });

    result.current.mutate({
      entityType: "protocol",
      entityId: "p-1",
      typedName: "wrong",
      reason: "cleanup",
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockShowError).toHaveBeenCalledWith("API error: 409 — name mismatch");
  });
});
