import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { ConditionDefinition } from "@/features/screening-assay/types";
import { SplitPicker, applySplit, withRunScope } from "./split-picker";

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const ATP = { name: "ATP Concentration" } as ConditionDefinition;
const STRAIN = { name: "Strain" } as ConditionDefinition;

function pick(combobox: HTMLElement, option: string) {
  fireEvent.click(combobox);
  fireEvent.click(within(screen.getByRole("listbox")).getByText(option));
}

describe("applySplit", () => {
  it("none drops the split and keeps the run filter", () => {
    expect(applySplit("none", { mode: "latest" }, [ATP])).toEqual({
      split: undefined,
      run_scope: { mode: "latest" },
    });
  });

  it("by run switches the run filter to hand-picked runs", () => {
    expect(applySplit("run", { mode: "past_n_days", days: 30 }, [ATP])).toEqual({
      split: { by: "run" },
      run_scope: { mode: "specific", run_ids: [] },
    });
  });

  it("by run keeps runs already picked", () => {
    const scope = { mode: "specific" as const, run_ids: ["r1", "r2"] };
    expect(applySplit("run", scope, [ATP]).run_scope).toBe(scope);
  });

  it("by condition picks the only condition and leaves a choice open otherwise", () => {
    expect(applySplit("condition", undefined, [ATP]).split).toEqual({
      by: "condition",
      condition: "ATP Concentration",
    });
    expect(applySplit("condition", undefined, [ATP, STRAIN]).split).toEqual({
      by: "condition",
      condition: "",
    });
  });

  it("by condition replaces the Latest run filter with Any run", () => {
    expect(applySplit("condition", { mode: "latest" }, [ATP]).run_scope).toBeUndefined();
  });
});

describe("SplitPicker", () => {
  it("shows None and sends no split by default", () => {
    render(
      <SplitPicker conditions={[ATP]} split={undefined} runScope={undefined} onChange={vi.fn()} />,
    );
    expect(screen.getByRole("combobox", { name: "Split columns" }).textContent).toBe("None");
  });

  it("choosing By run forces Specific run", () => {
    const onChange = vi.fn();
    render(
      <SplitPicker conditions={[ATP]} split={undefined} runScope={undefined} onChange={onChange} />,
    );
    pick(screen.getByRole("combobox", { name: "Split columns" }), "By run");
    expect(onChange).toHaveBeenCalledWith({
      split: { by: "run" },
      run_scope: { mode: "specific", run_ids: [] },
    });
  });

  it("lists the protocol's conditions once split by condition", () => {
    const onChange = vi.fn();
    render(
      <SplitPicker
        conditions={[ATP, STRAIN]}
        split={{ by: "condition", condition: "" }}
        runScope={undefined}
        onChange={onChange}
      />,
    );
    const condition = screen.getByRole("combobox", { name: "Split condition" });
    expect(condition).toHaveAttribute("aria-invalid", "true");
    pick(condition, "Strain");
    expect(onChange).toHaveBeenCalledWith({
      split: { by: "condition", condition: "Strain" },
      run_scope: undefined,
    });
  });

  it("offers By condition only when the protocol defines conditions", () => {
    render(
      <SplitPicker conditions={[]} split={undefined} runScope={undefined} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("combobox", { name: "Split columns" }));
    const option = within(screen.getByRole("listbox")).getByRole("option", {
      name: /By condition/,
    });
    expect(option).toHaveAttribute("data-disabled");
  });
});

describe("withRunScope", () => {
  it("turns split by run off when the run filter leaves Specific run", () => {
    expect(withRunScope({ by: "run" }, { mode: "latest" })).toEqual({
      split: undefined,
      run_scope: { mode: "latest" },
    });
  });

  it("keeps split by run while runs stay hand-picked", () => {
    const scope = { mode: "specific" as const, run_ids: ["r1"] };
    expect(withRunScope({ by: "run" }, scope)).toEqual({ split: { by: "run" }, run_scope: scope });
  });

  it("keeps a condition split under any multi-run filter", () => {
    const split = { by: "condition" as const, condition: "ATP" };
    expect(withRunScope(split, { mode: "past_n_days", days: 7 }).split).toBe(split);
  });
});
