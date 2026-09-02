import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AnyProtocolActivity, AnyProtocolEntry } from "../../types";
import { ActiveInCell } from "./active-in-cell";

function entry(over: Partial<AnyProtocolEntry>): AnyProtocolEntry {
  return {
    protocol_id: "p",
    protocol_name: "Proto",
    protocol_type: "biochemical",
    target_names: [],
    label: "IC50",
    source: "dose_response",
    readout_definition_id: "rd",
    value: 1,
    qualifier: null,
    unit: "uM",
    value_um: 1,
    curve_class: "full",
    run_count: 1,
    ...over,
  };
}

describe("ActiveInCell", () => {
  it("renders a dash when empty", () => {
    render(<ActiveInCell value={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows at most three entries, native units, then +N more", () => {
    const value: AnyProtocolActivity = {
      entries: [
        entry({ protocol_name: "Beta", value: 5, unit: "nM", value_um: 0.005 }),
        entry({ protocol_name: "Alpha", value: 5, unit: "uM" }),
        entry({ protocol_name: "Gamma", label: "EC90", value: 12.5, curve_class: "partial" }),
        entry({ protocol_name: "Delta", value: 40 }),
        entry({ protocol_name: "Eps", value: 41 }),
      ],
    };
    render(<ActiveInCell value={value} />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("5 nM")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(screen.queryByText("Delta")).not.toBeInTheDocument();
    expect(screen.getByText("+2 more")).toBeInTheDocument();
  });

  it("greys inactive curves, prefixes qualifiers, shows single target", () => {
    const value: AnyProtocolActivity = {
      entries: [
        entry({
          protocol_name: "Cyto",
          curve_class: "inactive",
          qualifier: ">",
          value: 100,
          target_names: ["Mtb"],
        }),
      ],
    };
    render(<ActiveInCell value={value} />);
    expect(screen.getByText(">100 uM")).toBeInTheDocument();
    expect(screen.getByText("Mtb")).toBeInTheDocument();
    expect(screen.getByTestId("active-in-row")).toHaveClass("text-muted-foreground");
  });
});
