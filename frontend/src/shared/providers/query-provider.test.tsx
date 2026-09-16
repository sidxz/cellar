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

  it("toasts a plain mutation error as before", () => {
    onMutationError(new Error("boom"));
    expect(mockShowError).toHaveBeenCalledWith("boom");
  });
});
