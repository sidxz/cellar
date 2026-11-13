import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const curvesProps: Array<Record<string, unknown>> = [];
vi.mock("./multi-run-curves", () => ({
  MultiRunCurves: (props: Record<string, unknown>) => {
    curvesProps.push(props);
    return <div data-testid="multi-run-curves" />;
  },
}));

import {
  CompoundCurvesProvider,
  type CompoundCurvesTarget,
  compoundCurvesSummary,
  useOpenCompoundCurves,
} from "./compound-curves-dialog";

const P = { id: "p1", name: "Protocol 1" };
const A = { id: "m1", name: "Compound A" };
const B = { id: "m2", name: "Compound B" };
const C = { id: "m3", name: "Compound C" };

function Opener({ target }: { target: CompoundCurvesTarget }) {
  const open = useOpenCompoundCurves();
  return (
    <button type="button" onClick={() => open?.(target)}>
      Open
    </button>
  );
}

function openFor(target: CompoundCurvesTarget) {
  render(
    <CompoundCurvesProvider>
      <Opener target={target} />
    </CompoundCurvesProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  return curvesProps.at(-1) as Record<string, unknown>;
}

beforeEach(() => {
  curvesProps.length = 0;
});

describe("compound curves dialog", () => {
  it("states what it shows, for one compound and for several", () => {
    expect(compoundCurvesSummary({ protocol: P, molecules: [A] })).toBe("Protocol 1 · Compound A");
    expect(compoundCurvesSummary({ protocol: P, molecules: [A, B] })).toBe(
      "Protocol 1 · Compound A and Compound B",
    );
    expect(compoundCurvesSummary({ protocol: P, molecules: [A, B, C] })).toBe(
      "Protocol 1 · Compound A, Compound B and Compound C",
    );
  });

  it("says in one line that runs outside the search's scope can be included", () => {
    openFor({ protocol: P, molecules: [A] });
    expect(screen.getByRole("dialog", { name: "Traces across runs" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Protocol 1 · Compound A. Includes every run except rejected runs, regardless of this search's run scope or aggregation.",
      ),
    ).toBeInTheDocument();
  });

  it("asks for the compounds' positions without rejected runs, references on, coloured by batch for one compound", () => {
    const props = openFor({ protocol: P, molecules: [A] });
    expect(props.protocolId).toBe("p1");
    expect(props.filter).toEqual({ moleculeIds: ["m1"] });
    expect(props.hideStatuses).toEqual(["rejected"]);
    expect(props.initial).toEqual({
      select: "compounds",
      showReferences: true,
      colour: { mode: "group", groupBy: "batch" },
    });
    // Named for what it shows, so exports of two compounds of one protocol differ.
    expect(props.exportName).toBe("traces-Protocol-1-Compound-A");
  });

  it("colours by compound for several compounds", () => {
    const props = openFor({ protocol: P, molecules: [A, B] });
    expect(props.filter).toEqual({ moleculeIds: ["m1", "m2"] });
    expect((props.initial as { colour: unknown }).colour).toEqual({
      mode: "group",
      groupBy: "compound",
    });
    expect(props.exportName).toBe("traces-Protocol-1-Compound-A-and-Compound-B");
  });

  it("says so when the compound has no curves outside rejected runs", () => {
    const props = openFor({ protocol: P, molecules: [A] });
    render(<div>{props.empty as ReactNode}</div>);
    expect(
      screen.getByText("No traces for Compound A in runs that are not rejected."),
    ).toBeInTheDocument();
  });

  it("returns null from useOpenCompoundCurves outside a provider", () => {
    let seen: unknown = "unset";
    function Probe() {
      seen = useOpenCompoundCurves();
      return null;
    }
    render(<Probe />);
    expect(seen).toBeNull();
  });
});
