import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type CampaignFilters, emptyFilters } from "../campaign-filter-bar";
import {
  type ReadoutOption,
  ResultsToolbar,
  measurementFilterText,
  parseFilterDrafts,
} from "./results-toolbar";

const readouts: ReadoutOption[] = [
  { id: "ch-sol", label: "Kinetic solubility · Solubility", unit: "µM" },
  { id: "ch-logd", label: "Lipophilicity (LogD) · LogD", unit: "-" },
];
const draft = (over: Record<string, string>) => ({
  channelId: "ch-sol",
  minimum: "",
  maximum: "",
  unit: "µM",
  qc: "any" as const,
  ...over,
});

describe("parseFilterDrafts", () => {
  it("turns bounds into numbers and keeps blank ones open", () => {
    expect(parseFilterDrafts([draft({ minimum: "50" })], readouts)).toEqual([
      { channelId: "ch-sol", minimum: 50, maximum: null, unit: "µM", qc: "any" },
    ]);
  });

  it("refuses an empty condition, a reversed range, a non-number and an unknown readout", () => {
    expect(parseFilterDrafts([draft({})], readouts)).toMatch(/minimum, a maximum or a QC/);
    expect(parseFilterDrafts([draft({ minimum: "9", maximum: "1" })], readouts)).toMatch(
      /must not exceed/,
    );
    expect(parseFilterDrafts([draft({ maximum: "abc" })], readouts)).toMatch(/must be numbers/);
    expect(parseFilterDrafts([draft({ channelId: "gone", maximum: "1" })], readouts)).toMatch(
      /Choose a readout/,
    );
  });
});

describe("measurementFilterText", () => {
  it("reads a range with its unit, and a QC state", () => {
    expect(
      measurementFilterText(
        { channelId: "ch-sol", minimum: 50, maximum: null, unit: "µM", qc: "verified" },
        "Solubility",
      ),
    ).toBe("Solubility ≥ 50 µM · QC verified");
  });

  it("leaves out an unknown unit", () => {
    expect(
      measurementFilterText(
        { channelId: "ch-logd", minimum: null, maximum: 5, unit: "-", qc: "any" },
        "LogD",
      ),
    ).toBe("LogD ≤ 5");
  });
});

function renderToolbar(filters: CampaignFilters) {
  const onFiltersChange = vi.fn();
  render(
    <ResultsToolbar
      filters={filters}
      onFiltersChange={onFiltersChange}
      readouts={readouts}
      labelOf={(id) => readouts.find((r) => r.id === id)?.label ?? "?"}
      sortable={readouts}
      sort={null}
      onSortChange={vi.fn()}
      columns={[]}
      hidden={new Set()}
      onColumnsChange={vi.fn()}
      maximized={false}
      onMaximizedChange={vi.fn()}
    />,
  );
  return onFiltersChange;
}

describe("ResultsToolbar", () => {
  const applied: CampaignFilters = {
    ...emptyFilters(),
    search: "SACC",
    measurements: [{ channelId: "ch-logd", minimum: null, maximum: 5, unit: "-", qc: "any" }],
  };

  it("shows the applied search and conditions as chips that remove themselves", () => {
    const onFiltersChange = renderToolbar(applied);
    expect(screen.getByRole("button", { name: "Filters (1)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove condition 1" }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ ...applied, measurements: [] });
    fireEvent.click(screen.getByRole("button", { name: "Remove search" }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ ...applied, search: "" });
  });

  it("clears search and conditions but leaves the outcome chips alone", () => {
    const filters = { ...applied, overriddenOnly: true };
    const onFiltersChange = renderToolbar(filters);
    fireEvent.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(onFiltersChange).toHaveBeenCalledWith({ ...filters, search: "", measurements: [] });
  });

  it("adds a condition from the Filters popover", () => {
    const onFiltersChange = renderToolbar(emptyFilters());
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.click(screen.getByRole("button", { name: "Add condition" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Minimum 1" }), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(onFiltersChange).toHaveBeenCalledWith({
      ...emptyFilters(),
      measurements: [{ channelId: "ch-sol", minimum: 50, maximum: null, unit: "µM", qc: "any" }],
    });
  });

  it("says what is wrong instead of applying a bad condition", () => {
    const onFiltersChange = renderToolbar(emptyFilters());
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.click(screen.getByRole("button", { name: "Add condition" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/minimum, a maximum or a QC/);
    expect(onFiltersChange).not.toHaveBeenCalled();
  });
});
