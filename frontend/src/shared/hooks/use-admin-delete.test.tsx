import { ApiError } from "@/shared/lib/api/custom-instance";
import type { BlockerPayload } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/api/admin/admin", () => ({
  adminHardDeleteApiV1AdminEntityTypeEntityIdDelete: vi.fn(),
  cascadeDeleteApiV1AdminEntityTypeEntityIdCascadeDelete: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));

import { adminHardDeleteApiV1AdminEntityTypeEntityIdDelete } from "@/shared/lib/api/admin/admin";
import { showError, showSuccess } from "@/shared/lib/toast";
import { getDeleteBlockedError, useAdminDelete } from "./use-admin-delete";

const mockDelete = adminHardDeleteApiV1AdminEntityTypeEntityIdDelete as ReturnType<typeof vi.fn>;
const mockShowError = showError as ReturnType<typeof vi.fn>;
const mockShowSuccess = showSuccess as ReturnType<typeof vi.fn>;

const SAMPLE_BLOCKER: BlockerPayload = {
  table: "batch",
  entity_type: "Batch",
  fk_column: "molecule_id",
  count: 2,
  samples: [{ id: "b-1", label: "Batch 1" }],
  truncated: false,
};

/** A 409 ApiError shaped exactly like the backend's blocked-delete response. */
function blockedApiError(): ApiError {
  return new ApiError("API error: 409", 409, {
    error: "delete_blocked_by_dependencies",
    message: "Cannot delete: 2 Batch(s) reference this entity.",
    blockers: [SAMPLE_BLOCKER],
  });
}

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

describe("getDeleteBlockedError", () => {
  it("matches a 409 ApiError carrying the blocker payload", () => {
    const blocked = getDeleteBlockedError(blockedApiError());
    expect(blocked).not.toBeNull();
    expect(blocked?.blockers).toEqual([SAMPLE_BLOCKER]);
  });

  it("rejects a non-409 ApiError", () => {
    expect(getDeleteBlockedError(new ApiError("API error: 404", 404, {}))).toBeNull();
  });

  it("rejects a 409 whose body is not the blocker contract", () => {
    expect(
      getDeleteBlockedError(new ApiError("API error: 409", 409, { error: "other" })),
    ).toBeNull();
  });

  it("rejects a plain Error (the old axios-shaped path can never match)", () => {
    expect(getDeleteBlockedError(new Error("boom"))).toBeNull();
    // Guards against regressing to `(err as any)?.response?.data`.
    expect(
      getDeleteBlockedError({ response: { data: { error: "delete_blocked_by_dependencies" } } }),
    ).toBeNull();
  });
});

describe("useAdminDelete", () => {
  beforeEach(() => {
    mockDelete.mockReset();
    mockShowError.mockReset();
    mockShowSuccess.mockReset();
  });

  it("toasts success and invalidates on a clean delete", async () => {
    mockDelete.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useAdminDelete({ onSuccess }), { wrapper });

    result.current.mutate({ entityType: "molecule", entityId: "m-1", reason: "cleanup" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalled();
    expect(mockShowSuccess).toHaveBeenCalledWith("Deleted");
    expect(onSuccess).toHaveBeenCalled();
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it("surfaces the blocker payload via getDeleteBlockedError and stays silent (no error toast)", async () => {
    mockDelete.mockRejectedValue(blockedApiError());
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useAdminDelete(), { wrapper });

    result.current.mutate({ entityType: "molecule", entityId: "m-1", reason: "cleanup" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // Blocked deletes are owned by the caller (it renders the blocker list);
    // the hook must NOT fire a misleading generic "Failed to delete" toast.
    expect(mockShowError).not.toHaveBeenCalled();
    const blocked = getDeleteBlockedError(result.current.error);
    expect(blocked?.blockers).toEqual([SAMPLE_BLOCKER]);
  });

  it("toasts the error message on a plain (non-blocked) failure", async () => {
    mockDelete.mockRejectedValue(new ApiError("API error: 500 — boom", 500, undefined));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useAdminDelete(), { wrapper });

    result.current.mutate({ entityType: "molecule", entityId: "m-1", reason: "cleanup" });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockShowError).toHaveBeenCalledWith("API error: 500 — boom");
  });
});
