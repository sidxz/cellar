import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApplicableRule } from "../lib/melt-hits";
import type { HitCriterion, ReadoutDefinition } from "../types";

const setMutate = vi.fn();
vi.mock("../hooks/use-runs", () => ({
  useSetRunHitCriteria: () => ({ mutate: setMutate, isPending: false }),
  useResetRunHitCriteria: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/shared/components/entity-name", () => ({
  MemberName: ({ id }: { id: string }) => <span>{`member ${id}`}</span>,
}));
vi.mock("./hit-criteria-dialog", () => ({
  RunHitCriteriaDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">run dialog</div> : null,
}));

import { MeltHitRule } from "./melt-hit-rule";

const outside: HitCriterion = {
  readout_name: "ΔTm (Main)",
  operator: "not_between",
  value: [-2, 2],
};
const other: HitCriterion = { readout_name: "Inhibition", operator: "gt", value: 50 };
const APPLICABLE: ApplicableRule[] = [{ rule: outside, window: "Main", measure: "delta_tm" }];
const READOUTS = [] as ReadoutDefinition[];

type RunLike = Parameters<typeof MeltHitRule>[0]["run"];
const run = (over: Partial<RunLike> = {}): RunLike => ({
  id: "r1",
  is_locked: false,
  hit_criteria: null,
  hit_criteria_set_by: null,
  hit_criteria_set_at: null,
  ...over,
});
const recorded = (criteria: HitCriterion[]) =>
  run({ hit_criteria: criteria, hit_criteria_set_by: "u1", hit_criteria_set_at: "2026-11-13" });

function show(props: Partial<Parameters<typeof MeltHitRule>[0]> = {}) {
  return render(
    <MeltHitRule
      run={run()}
      readoutDefinitions={READOUTS}
      recommendation={null}
      applicable={[]}
      other={[]}
      canEdit
      {...props}
    />,
  );
}

beforeEach(() => setMutate.mockClear());

describe("MeltHitRule", () => {
  it("shows the recorded rule, who set it, and Edit", () => {
    show({ run: recorded([outside, other]), applicable: APPLICABLE, other: [other] });
    expect(screen.getByText(/Hit rule: ΔTm \(Main\) outside -2 – 2/)).toBeInTheDocument();
    expect(screen.getByText("member u1")).toBeInTheDocument();
    expect(screen.getByText("Not evaluated here: Inhibition > 50")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("says when the recorded rule has nothing on Tm or ΔTm", () => {
    show({ run: recorded([other]), other: [other] });
    expect(screen.getByText("No hit rule on Tm or ΔTm for this run")).toBeInTheDocument();
    expect(screen.getByText("Not evaluated here: Inhibition > 50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("offers the protocol recommendation without applying it", () => {
    show({ recommendation: [outside] });
    expect(
      screen.getByText(/Protocol recommends: ΔTm \(Main\) outside -2 – 2/),
    ).toBeInTheDocument();
    expect(setMutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply to this run" }));
    expect(setMutate.mock.calls[0][0]).toEqual({ runId: "r1", criteria: [outside] });
    fireEvent.click(screen.getByRole("button", { name: "Customize…" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("with nothing recommended, offers to set a rule", () => {
    show();
    expect(screen.getByText("No hit rule for this run")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set hit rule" })).toBeInTheDocument();
  });

  it("shows a recorded show-all decision", () => {
    show({ run: recorded([]) });
    expect(screen.getByText(/No hit rule \(show all\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("a locked run disables the buttons", () => {
    show({ run: run({ is_locked: true }), recommendation: [outside] });
    expect(screen.getByRole("button", { name: "Apply to this run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Customize…" })).toBeDisabled();
  });

  it("a viewer sees the rule without buttons", () => {
    show({ recommendation: [outside], canEdit: false });
    expect(screen.getByText(/Protocol recommends/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("applies only what a run may record and says what it left out", () => {
    const series: HitCriterion = { readout_name: "Max ΔTm (Main)", operator: "lt", value: -5 };
    const readouts = [
      { name: "Max ΔTm (Main)", melt_config: { measure: "max_delta_tm" } },
    ] as unknown as ReadoutDefinition[];
    show({ recommendation: [outside, series], readoutDefinitions: readouts });
    expect(
      screen.getByText("Left out (a series value is not a run rule): Max ΔTm (Main) < -5"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply to this run" }));
    expect(setMutate.mock.calls[0][0]).toEqual({ runId: "r1", criteria: [outside] });
  });
});
