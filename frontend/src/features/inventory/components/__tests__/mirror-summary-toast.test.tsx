import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToast } from "../mirror-summary-toast";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    message: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("renderToast", () => {
  it("does nothing for an empty summary", () => {
    renderToast({ created: 0, skipped: [] });
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.message).not.toHaveBeenCalled();
  });

  it("does nothing on clean success (no skipped rows)", () => {
    renderToast({ created: 3, skipped: [] });
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.message).not.toHaveBeenCalled();
  });

  it("renders message toast with details when there are skips", () => {
    renderToast({
      created: 2,
      skipped: [
        {
          batch_number: "CC-036715-002",
          mirror_string: "SACC-0036913-002",
          reason: "workspace_conflict",
        },
      ],
    });
    expect(toast.message).toHaveBeenCalledWith(
      expect.stringContaining("2 created"),
      expect.objectContaining({
        description: expect.stringContaining("1 skipped"),
      }),
    );
  });
});
