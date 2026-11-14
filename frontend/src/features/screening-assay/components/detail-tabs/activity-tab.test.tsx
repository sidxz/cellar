import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ActivitySummaryV2, HitCriterion, Protocol, ReadoutDefInfo } from "../../types";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: () => <div data-testid="structure" />,
}));
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: () => <div data-testid="structure" />,
}));
vi.mock("@/shared/lib/plotly", () => ({ Plot: () => <div data-testid="plot" /> }));
vi.mock("@/shared/components/data-grid/data-grid", async () => ({
  DataGrid: (await import("../../test/test-data-grid")).TableGrid,
}));
vi.mock("@/shared/components/collection-picker-dialog", () => ({
  CollectionPickerDialog: () => null,
}));
vi.mock("../hit-criteria-dialog", () => ({ HitCriteriaDialog: () => null }));

const activity: { data?: ActivitySummaryV2 } = {};
vi.mock("../../hooks/use-protocol-activity", () => ({
  useProtocolActivity: () => ({ data: activity.data, isLoading: false }),
}));
vi.mock("../../hooks/use-compound-flags", () => ({
  useCompoundFlags: () => ({ data: [] }),
  useCreateFlag: () => ({ mutate: vi.fn() }),
  useDeleteFlag: () => ({ mutate: vi.fn() }),
}));
vi.mock("../../hooks/use-compound-curves", () => ({
  useCompoundCurves: () => ({ data: undefined, isLoading: false }),
  useMultiCompoundCurves: () => ({ data: undefined, isLoading: false }),
}));

import { ActivityTab } from "./activity-tab";

const melt = (name: string, measure: string, unit = "°C"): ReadoutDefInfo =>
  ({
    name,
    data_type: "numeric",
    unit,
    best_direction: "magnitude",
    intercepts: [],
    melt_config: { window: "Main", measure, channel_key: "ratio", low: 50, high: 85 },
  }) as unknown as ReadoutDefInfo;

const READOUTS = [
  {
    name: "Inflection Point #1 for Ratio",
    data_type: "numeric",
    unit: "°C",
    best_direction: "high",
    intercepts: [],
  } as ReadoutDefInfo,
  melt("Tm (Main)", "tm"),
  melt("ΔTm (Main)", "delta_tm"),
  melt("Max ΔTm (Main)", "max_delta_tm"),
];

const compound = (id: string, max: number, mean: number) => ({
  molecule_id: id,
  molecule_name: "",
  registration_number: id,
  run_count: 2,
  last_tested: "2026-11-13",
  smiles: "CCO",
  batch_number: null,
  synonyms: [],
  readouts: {
    "Inflection Point #1 for Ratio": { best: 70.4, mean: 70.4 },
    "Tm (Main)": { best: 70.4, mean: 70.4 },
    "ΔTm (Main)": { best: max, mean },
    "Max ΔTm (Main)": { best: max, mean, n: 2, sd: 1.1 },
  },
});

function show(criteria: HitCriterion[] | null = null) {
  activity.data = {
    items: [compound("CC-1", -8.5, -5.25), compound("CC-2", -0.9, -0.9)],
    readout_definitions: READOUTS,
    total_compounds: 2,
  } as unknown as ActivitySummaryV2;
  const protocol = {
    id: "p1",
    readout_definitions: [],
    recommended_hit_criteria: criteria,
  } as unknown as Protocol;
  return render(<ActivityTab protocol={protocol} protocolId="p1" />);
}

const headers = () => screen.getAllByRole("columnheader").map((h) => h.textContent);
const row = (id: string) => document.querySelector(`[data-row-id="${id}"]`) as HTMLElement;

beforeEach(() => localStorage.clear());

describe("Activity grid", () => {
  it("groups a window under one header, one column per result, extras on demand", () => {
    show();
    const h = headers();
    expect(h).toContain("Main window · 50–85 °C");
    expect(h).toContain("Max ΔTm (°C)");
    expect(h).not.toContain("Tm (°C)");
    expect(h).not.toContain("Inflection Point #1 for Ratio (°C)");
    expect(h.some((x) => x?.includes("Mean"))).toBe(false);
    // Largest shift first, signed.
    expect(within(row("CC-1")).getByText("−8.5")).toBeInTheDocument();
    expect(screen.queryByTestId("structure")).toBeNull();
  });

  it("the summary switch shows means instead of best values", () => {
    show();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Mean" }));
    expect(within(row("CC-1")).getByText("−5.25")).toBeInTheDocument();
  });

  it("lists every compound with its hit status and filters by status", () => {
    const rule: HitCriterion = {
      readout_name: "Max ΔTm (Main)",
      operator: "not_between",
      value: [-2, 2],
    };
    show([rule]);
    expect(within(row("CC-1")).getByText("Meets")).toBeInTheDocument();
    expect(within(row("CC-2")).getByText("Doesn't meet")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Meets criteria (1)" }));
    expect(row("CC-2")).toBeNull();
    expect(row("CC-1")).not.toBeNull();
  });

  it("the Columns menu shows a hidden column and remembers it", () => {
    const first = show();
    fireEvent.click(screen.getByRole("button", { name: "Columns" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Tm (°C)" }));
    expect(headers()).toContain("Tm (°C)");
    first.unmount();
    show();
    expect(headers()).toContain("Tm (°C)");
  });

  it("the Structures switch adds structure drawings", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Structures" }));
    expect(screen.getAllByTestId("structure").length).toBeGreaterThan(0);
  });
});
