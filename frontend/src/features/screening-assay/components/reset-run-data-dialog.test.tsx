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

import { ResetRunDataDialog, resetDamageText, resetDoneText } from "./reset-run-data-dialog";

function plateMap(kind: string, curves: boolean) {
  return {
    dose_unit: "uM",
    has_measured_curves: curves,
    plates: [{ plate_id: "pl1", holder_kind: kind, holder_label: "Holder of 3 positions" }],
  };
}

const out = (n: number, measured: number) => ({
  plates_deleted: n,
  wells_deleted: n,
  readouts_deleted: n,
  curves_deleted: n,
  measured_curves_deleted: measured,
  melting_steps_deleted: 0,
});

describe("resetDamageText", () => {
  it.each([
    // holder, measured curves, must contain, must not match
    ["H1", false, ["the holder (H1)", "positions"], /plates|wells|traces/],
    ["H1", true, ["the holder (H1)", "positions", "traces"], /plates|wells/],
    [null, false, ["plates (2)", "wells"], /holder|positions|traces/],
    [null, true, ["plates (2)", "wells", "traces"], /holder|positions/],
  ] as const)("holder %s, measured curves %s", (holder, measured, has, hasNot) => {
    const text = resetDamageText(holder, 2, measured);
    for (const term of has) expect(text).toContain(term);
    expect(text).not.toMatch(hasNot);
  });
});

describe("resetDoneText", () => {
  it.each([
    // isHolder, counts, measured, must contain, must not match
    [
      true,
      3,
      12,
      ["3 positions", "3 readouts", "3 dose-response curves", "12 traces"],
      /plates|wells/,
    ],
    [
      true,
      1,
      1,
      ["1 position,", "1 readout,", "1 dose-response curve,", "1 trace "],
      /plates|wells/,
    ],
    [true, 3, 0, ["3 positions"], /trace/],
    [false, 3, 4, ["3 plates", "3 wells", "3 readouts", "3 curves", "4 traces"], /position/],
    [false, 3, 0, ["3 plates", "3 wells"], /trace|position/],
  ] as const)("holder %s, %i of each, %i traces", (isHolder, n, measured, has, hasNot) => {
    const text = resetDoneText(out(n, measured), isHolder);
    for (const term of has) expect(text).toContain(term);
    expect(text).not.toMatch(hasNot);
  });
});

function confirm(plateCount: number) {
  render(<ResetRunDataDialog runId="r1" open onOpenChange={vi.fn()} plateCount={plateCount} />);
  fireEvent.click(screen.getByRole("button", { name: /reset run data/i }));
}

beforeEach(() => showSuccess.mockReset());

describe("ResetRunDataDialog", () => {
  it.each([
    ["cassette", true, "Holder of 3 positions", 0],
    ["plate", false, null, 1],
  ] as const)(
    "a %s run with measured curves %s words the dialog and toast for its holder",
    (kind, curves, holderLabel, plateCount) => {
      state.plateMap = plateMap(kind, curves);
      state.out = out(2, 5);
      confirm(plateCount);
      expect(screen.getByRole("alertdialog").textContent).toContain(
        resetDamageText(holderLabel, plateCount, curves),
      );
      expect(showSuccess).toHaveBeenCalledWith(resetDoneText(out(2, 5), holderLabel !== null));
    },
  );
});
