import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { HitCriterion, ReadoutDefinition } from "../types";
import { RunHitCriteriaDialog } from "./hit-criteria-dialog";

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
