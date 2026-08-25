import { ApiError } from "@/shared/lib/api/custom-instance";
import type { KioskConfirmResponse, KioskScanResponse } from "@/shared/lib/api/model";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KIOSK_TOKEN_KEY } from "./kiosk-api";

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/shared/lib/api/custom-instance")>();
  return { ...actual, customInstance: vi.fn() };
});

import { customInstance } from "@/shared/lib/api/custom-instance";
import KioskScreen from "./kiosk-screen";

const mockCustomInstance = vi.mocked(customInstance);

const SCAN_RESPONSE: KioskScanResponse = {
  plate_id: "p1",
  barcode: "005261",
  plate_label: "SAC1-12",
  loan_id: "l1",
  item_id: "i1",
  item_status: "loaned",
  action: "checkout",
  borrower_org_id: "org-1",
  borrower_org_name: "TAMU",
  due_date: "2026-09-08",
};

const CONFIRM_RESPONSE: KioskConfirmResponse = {
  loan_id: "l1",
  item_id: "i1",
  new_status: "checked_out",
};

function submitBarcode(value: string) {
  const input = screen.getByLabelText("Barcode");
  fireEvent.change(input, { target: { value } });
  const form = input.closest("form");
  if (!form) throw new Error("barcode input is not inside a form");
  fireEvent.submit(form);
}

describe("KioskScreen", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockCustomInstance.mockReset();
    // shouldAdvanceTime keeps the mocked clock ticking in step with real time,
    // so `await waitFor(...)` (which polls via a real setInterval) still works
    // for the scan/confirm promise chain — `vi.advanceTimersByTime` below then
    // fast-forwards past the 3s/5s auto-clear without a real sleep.
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the token form when no token is stored; saving stores it and shows the scan input focused", async () => {
    render(<KioskScreen />);

    expect(screen.getByLabelText("Device token")).toBeInTheDocument();
    expect(screen.queryByLabelText("Barcode")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Device token"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(window.localStorage.getItem(KIOSK_TOKEN_KEY)).toBe("abc");
    const barcodeInput = await waitFor(() => {
      const el = screen.getByLabelText("Barcode");
      expect(el).toHaveFocus();
      return el;
    });
    expect(barcodeInput).toBeInTheDocument();
  });

  it("scans, confirms, shows the result, then auto-clears after 3s", async () => {
    window.localStorage.setItem(KIOSK_TOKEN_KEY, "abc");
    mockCustomInstance.mockImplementation(async ({ url }) => {
      if (url === "/api/v1/kiosk/scan") return SCAN_RESPONSE;
      if (url === "/api/v1/kiosk/confirm") return CONFIRM_RESPONSE;
      throw new Error(`unexpected url ${url}`);
    });

    render(<KioskScreen />);
    submitBarcode("005261");

    await waitFor(() => {
      expect(screen.getByTestId("kiosk-result")).toBeInTheDocument();
    });

    expect(mockCustomInstance).toHaveBeenNthCalledWith(1, {
      url: "/api/v1/kiosk/scan",
      method: "POST",
      data: { barcode: "005261" },
      headers: { "X-Kiosk-Token": "abc" },
    });
    expect(mockCustomInstance).toHaveBeenNthCalledWith(2, {
      url: "/api/v1/kiosk/confirm",
      method: "POST",
      data: { loan_id: "l1", item_id: "i1" },
      headers: { "X-Kiosk-Token": "abc" },
    });

    expect(screen.getByText("Checked out")).toBeInTheDocument();
    expect(screen.getByText("SAC1-12")).toBeInTheDocument();
    expect(screen.getByText("TAMU")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(screen.queryByTestId("kiosk-result")).not.toBeInTheDocument();
    const barcodeInput = screen.getByLabelText("Barcode") as HTMLInputElement;
    expect(barcodeInput.value).toBe("");
    expect(barcodeInput).toHaveFocus();
  });

  it("shows the server detail on a 409 (Cellar's {error, message} shape) and clears it after 5s", async () => {
    window.localStorage.setItem(KIOSK_TOKEN_KEY, "abc");
    mockCustomInstance.mockRejectedValueOnce(
      new ApiError("API error: 409", 409, {
        error: "ConflictError",
        message: "No pending kiosk action for plate '1'",
      }),
    );

    render(<KioskScreen />);
    submitBarcode("1");

    await waitFor(() => {
      expect(screen.getByTestId("kiosk-result")).toBeInTheDocument();
    });
    expect(mockCustomInstance).toHaveBeenCalledTimes(1);
    expect(screen.getByText("No pending kiosk action for plate '1'")).toBeInTheDocument();
    expect(screen.getByTestId("kiosk-result")).toHaveClass("bg-red-600");

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(screen.queryByTestId("kiosk-result")).not.toBeInTheDocument();
  });

  it("still shows the detail on a validation-style {detail} body", async () => {
    window.localStorage.setItem(KIOSK_TOKEN_KEY, "abc");
    mockCustomInstance.mockRejectedValueOnce(
      new ApiError("API error: 422", 422, { detail: "barcode: field required" }),
    );

    render(<KioskScreen />);
    submitBarcode("1");

    await waitFor(() => {
      expect(screen.getByTestId("kiosk-result")).toBeInTheDocument();
    });
    expect(screen.getByText("barcode: field required")).toBeInTheDocument();
  });

  it("forgets the token and shows the token form again on a 403", async () => {
    window.localStorage.setItem(KIOSK_TOKEN_KEY, "abc");
    mockCustomInstance.mockRejectedValueOnce(new ApiError("API error: 403", 403, undefined));

    render(<KioskScreen />);
    submitBarcode("005261");

    await waitFor(() => {
      expect(screen.getByLabelText("Device token")).toBeInTheDocument();
    });
    expect(mockCustomInstance).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem(KIOSK_TOKEN_KEY)).toBeNull();
    expect(screen.queryByTestId("kiosk-result")).not.toBeInTheDocument();
  });

  it("shows a not-recognized message on a 404", async () => {
    window.localStorage.setItem(KIOSK_TOKEN_KEY, "abc");
    mockCustomInstance.mockRejectedValueOnce(
      new ApiError("API error: 404", 404, { detail: "Not Found" }),
    );

    render(<KioskScreen />);
    submitBarcode("999999");

    await waitFor(() => {
      expect(screen.getByTestId("kiosk-result")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Plate not recognized for this device's organization"),
    ).toBeInTheDocument();
  });
});
