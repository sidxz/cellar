import { ApiError } from "@/shared/lib/api/custom-instance";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
}));

import { showError } from "@/shared/lib/toast";
import { onMutationError } from "./query-provider";

const mockShowError = showError as ReturnType<typeof vi.fn>;

describe("onMutationError", () => {
  beforeEach(() => {
    mockShowError.mockReset();
  });

  it("stays silent on a blocked-delete 409 — the dialog already lists the blockers", () => {
    onMutationError(
      new ApiError("API error: 409", 409, {
        error: "delete_blocked_by_dependencies",
        blockers: [],
      }),
    );
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it("stays silent on a stale edit — the caller explains it and offers a reload", () => {
    onMutationError(new ApiError("API error: 409", 409, { error: "StaleEditError" }));
    expect(mockShowError).not.toHaveBeenCalled();
  });

  it("stays silent on a race 409 only for a mutation that explains it as a stale edit", () => {
    const race = new ApiError("API error: 409", 409, { error: "ConcurrencyConflictError" });
    onMutationError(race, undefined, undefined, { meta: { raceIsStale: true } });
    expect(mockShowError).not.toHaveBeenCalled();
    onMutationError(race);
    expect(mockShowError).toHaveBeenCalledWith("API error: 409");
  });

  it("toasts a plain mutation error as before", () => {
    onMutationError(new Error("boom"));
    expect(mockShowError).toHaveBeenCalledWith("boom");
  });
});
