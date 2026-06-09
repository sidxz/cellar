import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { ConditionDefinition, Protocol, Run } from "../types";
import { ConditionsRelation } from "./run-relations";

// Radix Popover needs pointer-event stubs in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const mutate = vi.fn();
vi.mock("../hooks/use-runs", () => ({
  useUpdateRun: () => ({ mutate, isPending: false }),
}));

const def = (over: Partial<ConditionDefinition> & { name: string }): ConditionDefinition => ({
  id: over.id ?? over.name,
  name: over.name,
  data_type: over.data_type ?? "text",
  unit: over.unit ?? null,
  pick_list_values: over.pick_list_values ?? null,
});

const protocol = (defs: ConditionDefinition[]): Protocol =>
  ({ condition_definitions: defs }) as Protocol;

const run = (over: Partial<Run> = {}): Run => ({ id: "r1", conditions: null, ...over }) as Run;

describe("ConditionsRelation", () => {
  it("renders nothing when no definitions and no conditions", () => {
    const { container } = render(
      <ConditionsRelation run={run()} protocol={protocol([])} canEdit />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows chips for existing conditions to a read-only viewer, without an edit trigger", () => {
    render(
      <ConditionsRelation
        run={run({ conditions: { "Carbon Source": "glucose" } })}
        protocol={protocol([])}
        canEdit={false}
      />,
    );
    expect(screen.getByText("Carbon Source:")).toBeInTheDocument();
    expect(screen.getByText("glucose")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers an Add affordance for an editor when the protocol declares conditions but none are set", () => {
    render(
      <ConditionsRelation
        run={run()}
        protocol={protocol([def({ name: "Carbon Source" })])}
        canEdit
      />,
    );
    expect(screen.getByRole("button", { name: "Add conditions" })).toBeInTheDocument();
  });

  it("seeds the editor from the run and saves the built payload", () => {
    mutate.mockClear();
    render(
      <ConditionsRelation
        run={run({ conditions: { "Carbon Source": "glucose" } })}
        protocol={protocol([def({ name: "Carbon Source" })])}
        canEdit
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit conditions" }));

    const input = screen.getByDisplayValue("glucose");
    fireEvent.change(input, { target: { value: "glycerol" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({
      runId: "r1",
      data: { conditions: { "Carbon Source": "glycerol" } },
    });
  });

  it("clears conditions to null when the only value is emptied", () => {
    mutate.mockClear();
    render(
      <ConditionsRelation
        run={run({ conditions: { "Carbon Source": "glucose" } })}
        protocol={protocol([def({ name: "Carbon Source" })])}
        canEdit
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit conditions" }));
    fireEvent.change(screen.getByDisplayValue("glucose"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mutate.mock.calls[0][0]).toEqual({ runId: "r1", data: { conditions: null } });
  });
});
