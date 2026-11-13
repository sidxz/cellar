import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state: { plateMap: unknown; out: Record<string, number> } = { plateMap: undefined, out: {} };
const showSuccess = vi.fn();

vi.mock("../hooks/use-plate-setup", () => ({ usePlateMap: () => ({ data: state.plateMap }) }));
vi.mock("../hooks/use-run-import", () => ({
  useResetRunData: () => ({
    isPending: false,
    mutate: (_: unknown, opts: { onSuccess: (out: Record<string, number>) => void }) =>
      opts.onSuccess(state.out),
  }),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: (...args: unknown[]) => showSuccess(...args),
  showError: vi.fn(),
}));

import { ResetRunDataDialog } from "./reset-run-data-dialog";

function plateMap(kind: string, curves: boolean) {
  return {
    dose_unit: "uM",
    has_measured_curves: curves,
    plates: [{ plate_id: "pl1", holder_kind: kind, holder_label: "Holder of 3 positions" }],
  };
}

const out = (measured: number) => ({
  plates_deleted: 1,
  wells_deleted: 3,
  readouts_deleted: 2,
  curves_deleted: 0,
  measured_curves_deleted: measured,
});

function confirm(plateCount = 1) {
  render(<ResetRunDataDialog runId="r1" open onOpenChange={vi.fn()} plateCount={plateCount} />);
  fireEvent.click(screen.getByRole("button", { name: /reset run data/i }));
}

beforeEach(() => showSuccess.mockReset());

describe("ResetRunDataDialog", () => {
  it("speaks of the holder and its positions, and names measured curves, for a non-plate run", () => {
    state.plateMap = plateMap("cassette", true);
    state.out = out(12);
    confirm(0);
    const text = screen.getByRole("alertdialog").textContent ?? "";
    expect(text).toContain("the holder (Holder of 3 positions) and its positions");
    expect(text).toContain("traces");
    expect(text).not.toMatch(/plates|wells/);
    const toast = showSuccess.mock.calls[0][0] as string;
    expect(toast).toBe(
      "Reset run data — 3 positions, 2 readouts, 0 dose-response curves, 12 traces removed.",
    );
  });

  it("keeps the plate wording for a plate run and adds measured curves only when there are some", () => {
    state.plateMap = plateMap("plate", false);
    state.out = out(0);
    confirm(1);
    const text = screen.getByRole("alertdialog").textContent ?? "";
    expect(text).toContain(
      "This will delete all plates (1), wells, readout data, dose-response curves, and QC metrics",
    );
    expect(showSuccess.mock.calls[0][0]).toBe(
      "Reset run data — 1 plates, 3 wells, 2 readouts, 0 curves removed.",
    );
  });

  it("names measured curves on a plate run that has them", () => {
    state.plateMap = plateMap("plate", true);
    state.out = out(4);
    confirm(1);
    expect(screen.getByRole("alertdialog").textContent).toContain(
      "dose-response curves, traces, and QC metrics",
    );
    expect(showSuccess.mock.calls[0][0]).toContain("0 curves, 4 traces removed.");
  });

  it("counts one of each in the singular for a non-plate run", () => {
    state.plateMap = plateMap("cassette", true);
    state.out = {
      plates_deleted: 1,
      wells_deleted: 1,
      readouts_deleted: 1,
      curves_deleted: 1,
      measured_curves_deleted: 1,
    };
    confirm(0);
    expect(showSuccess.mock.calls[0][0]).toBe(
      "Reset run data — 1 position, 1 readout, 1 dose-response curve, 1 trace removed.",
    );
  });
});
