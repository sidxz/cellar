import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { HitCriterion, ReadoutDefinition } from "../types";
import { HitCriteriaDialog, RunHitCriteriaDialog } from "./hit-criteria-dialog";

// Radix Dialog/Select need pointer-event stubs in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const setMutate = vi.fn();
const resetMutate = vi.fn();
const protocolMutate = vi.fn();

vi.mock("../hooks/use-runs", () => ({
  useSetRunHitCriteria: () => ({ mutate: setMutate, isPending: false }),
  useResetRunHitCriteria: () => ({ mutate: resetMutate, isPending: false }),
}));
vi.mock("../hooks/use-protocols", () => ({
  useUpdateProtocol: () => ({ mutate: protocolMutate, isPending: false }),
}));

const rule: HitCriterion = { readout_name: "% Inhibition", operator: "gt", value: 50 };

beforeEach(() => {
  setMutate.mockClear();
  resetMutate.mockClear();
  protocolMutate.mockClear();
});

describe("RunHitCriteriaDialog", () => {
  it("saves the run's criteria to the run (not the protocol)", () => {
    render(
      <RunHitCriteriaDialog
        runId="r1"
        readoutDefinitions={[] as ReadoutDefinition[]}
        currentCriteria={[rule]}
        recommendation={null}
        open
        onOpenChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save for this run/i }));

    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toMatchObject({ runId: "r1", criteria: [rule] });
    // The run dialog must NOT touch the protocol's recommended criteria.
    expect(protocolMutate).not.toHaveBeenCalled();
  });

  it("seeds from the protocol recommendation when the run is unset", () => {
    render(
      <RunHitCriteriaDialog
        runId="r2"
        readoutDefinitions={[] as ReadoutDefinition[]}
        currentCriteria={null}
        recommendation={[rule]}
        open
        onOpenChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save for this run/i }));

    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toMatchObject({ runId: "r2", criteria: [rule] });
  });

  it("offers Reset to protocol recommendation only when the run has a recorded decision", () => {
    const { rerender } = render(
      <RunHitCriteriaDialog
        runId="r3"
        readoutDefinitions={[] as ReadoutDefinition[]}
        currentCriteria={[rule]}
        recommendation={null}
        open
        onOpenChange={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /reset to protocol recommendation/i }));
    expect(resetMutate).toHaveBeenCalledTimes(1);
    expect(resetMutate.mock.calls[0][0]).toBe("r3");

    // Unset run → nothing to reset, so the button is absent.
    rerender(
      <RunHitCriteriaDialog
        runId="r3"
        readoutDefinitions={[] as ReadoutDefinition[]}
        currentCriteria={null}
        recommendation={[rule]}
        open
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /reset to protocol recommendation/i }),
    ).not.toBeInTheDocument();
  });
});

describe("outside operator", () => {
  const outside: HitCriterion = {
    readout_name: "ΔTm (Main)",
    operator: "not_between",
    value: [-2, 2],
  };
  const dtm = {
    id: "rd1",
    name: "ΔTm (Main)",
    data_type: "numeric",
    normalizations: [],
    melt_config: { measure: "delta_tm" },
  } as unknown as ReadoutDefinition;

  it("protocol dialog offers outside with two inputs and a hint; the run dialog does not", () => {
    render(
      <HitCriteriaDialog
        protocolId="p1"
        readoutDefinitions={[dtm]}
        currentCriteria={[outside]}
        open
        onOpenChange={() => {}}
      />,
    );
    // two bound inputs, and the hint under the ΔTm criterion
    expect(screen.getAllByRole("spinbutton")).toHaveLength(2);
    expect(screen.getByText(/Typical: outside −2 to 2 °C/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("combobox")[1]);
    expect(within(screen.getByRole("listbox")).getByText("outside")).toBeInTheDocument();
  });

  it("run dialog keeps today's operator list", () => {
    render(
      <RunHitCriteriaDialog
        runId="r1"
        readoutDefinitions={[dtm]}
        currentCriteria={[{ readout_name: "ΔTm (Main)", operator: "gt", value: 1 }]}
        recommendation={null}
        open
        onOpenChange={() => {}}
      />,
    );
    fireEvent.click(screen.getAllByRole("combobox")[1]);
    expect(within(screen.getByRole("listbox")).queryByText("outside")).not.toBeInTheDocument();
  });

  it("protocol dialog saves outside as [low, high]", () => {
    render(
      <HitCriteriaDialog
        protocolId="p1"
        readoutDefinitions={[dtm]}
        currentCriteria={[outside]}
        open
        onOpenChange={() => {}}
      />,
    );
    const [low, high] = screen.getAllByRole("spinbutton");
    fireEvent.change(low, { target: { value: "-3" } });
    fireEvent.change(high, { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: /save criteria/i }));
    expect(protocolMutate.mock.calls[0][0]).toMatchObject({
      recommended_hit_criteria: [{ operator: "not_between", value: [-3, 4] }],
    });
  });

  it("run dialog drops an outside rule from the recommendation and says so", () => {
    render(
      <RunHitCriteriaDialog
        runId="r1"
        readoutDefinitions={[dtm]}
        currentCriteria={null}
        recommendation={[rule, outside]}
        open
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByText(/“outside” rule is left out/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save for this run/i }));
    expect(setMutate.mock.calls[0][0]).toMatchObject({ runId: "r1", criteria: [rule] });
  });

  it("protocol dialog cannot save outside with low not below high", () => {
    render(
      <HitCriteriaDialog
        protocolId="p1"
        readoutDefinitions={[dtm]}
        currentCriteria={[{ readout_name: "ΔTm (Main)", operator: "not_between", value: [0, 0] }]}
        open
        onOpenChange={() => {}}
      />,
    );
    const save = screen.getByRole("button", { name: /save criteria/i });
    expect(save).toBeDisabled();
    const [low, high] = screen.getAllByRole("spinbutton");
    fireEvent.change(low, { target: { value: "-2" } });
    fireEvent.change(high, { target: { value: "2" } });
    expect(save).toBeEnabled();
  });
});
