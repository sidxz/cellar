import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DoseResponsePointInventory } from "./dose-response-point-inventory";

const rawData = [
  { concentration: 1e-9, response: 2.4 },
  { concentration: 1e-8, response: 5.1 },
  { concentration: 1e-7, response: 18.0 },
];

describe("DoseResponsePointInventory", () => {
  it("renders one row per data point with status pill", () => {
    render(
      <DoseResponsePointInventory
        rawData={rawData}
        exclusions={[
          {
            idx: 1,
            source: "manual",
            excluded: true,
            reason: "outlier",
            note: "spike",
            author_id: "u1",
            ts: "2026-05-19T10:00:00Z",
            concentration: null,
            response: null,
          },
        ]}
        residuals={[0.3, -4.1, 0.2]}
        onToggle={vi.fn()}
      />,
    );
    // Expect 3 data rows
    expect(screen.getAllByRole("row")).toHaveLength(4); // header + 3
    expect(screen.getByText(/excluded/i)).toBeInTheDocument();
    expect(screen.getByText(/manual/i)).toBeInTheDocument();
  });

  it("renders suggestion with warning styling", () => {
    render(
      <DoseResponsePointInventory
        rawData={rawData}
        exclusions={[
          {
            idx: 0,
            source: "auto_3sigma",
            excluded: false,
            reason: "auto_3sigma",
            note: null,
            author_id: null,
            ts: "2026-05-19T10:00:00Z",
            concentration: null,
            response: null,
          },
        ]}
        residuals={[3.5, 0.1, 0.0]}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/suggested/i)).toBeInTheDocument();
  });

  it("clicking a row calls onToggle with the point's idx", async () => {
    const onToggle = vi.fn();
    render(
      <DoseResponsePointInventory
        rawData={rawData}
        exclusions={[]}
        residuals={[0.1, 0.2, 0.3]}
        onToggle={onToggle}
      />,
    );
    const rows = screen.getAllByRole("row");
    // rows[0] is the header
    fireEvent.click(rows[1]);
    expect(onToggle).toHaveBeenCalledWith(0);
  });

  it("renders legacy (idx=null) entries in a separate read-only section", () => {
    render(
      <DoseResponsePointInventory
        rawData={rawData}
        exclusions={[
          {
            idx: null,
            source: "auto_3sigma",
            excluded: true,
            reason: "auto_3sigma",
            note: null,
            author_id: null,
            ts: "2026-05-19T10:00:00Z",
            concentration: 5e-6,
            response: 42.5,
          },
        ]}
        residuals={[0.1, 0.2, 0.3]}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/legacy exclusions/i)).toBeInTheDocument();
    // The concentration appears in the legacy section
    expect(screen.getByText(/5\.00e-?6/i)).toBeInTheDocument();
  });

  it("legacy entries are NOT clickable", () => {
    const onToggle = vi.fn();
    render(
      <DoseResponsePointInventory
        rawData={[]}
        exclusions={[
          {
            idx: null,
            source: "auto_3sigma",
            excluded: true,
            reason: "auto_3sigma",
            note: null,
            author_id: null,
            ts: "2026-05-19T10:00:00Z",
            concentration: 5e-6,
            response: 42.5,
          },
        ]}
        onToggle={onToggle}
      />,
    );
    const legacyRow =
      screen.getByText(/5\.00e-?6/i).closest("tr") ??
      screen.getByText(/5\.00e-?6/i);
    fireEvent.click(legacyRow);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("renders empty state when rawData and exclusions are both empty", () => {
    render(
      <DoseResponsePointInventory
        rawData={[]}
        exclusions={[]}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/no points/i)).toBeInTheDocument();
  });
});
