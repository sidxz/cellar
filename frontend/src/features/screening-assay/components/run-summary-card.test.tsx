import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Run } from "../types";
import { RunSummaryCard } from "./run-summary-card";

// Isolate the facts band: stub the relation editors (which need query hooks),
// the notes line, and the protocol-name resolver. We're testing the card's own
// facts/Z' rendering, not its children.
vi.mock("./run-relations", () => ({
  TargetsRelation: () => null,
  CollectionsRelation: () => null,
  ConditionsRelation: () => null,
  TagsRelation: () => null,
}));
vi.mock("./run-notes-line", () => ({ RunNotesLine: () => null }));
vi.mock("@/shared/components/entity-name", () => ({
  ProtocolName: ({ id }: { id: string }) => <span>{id}</span>,
}));

const run = (over: Partial<Run> = {}): Run =>
  ({
    id: "r1",
    protocol_id: "p1",
    run_date: "2026-05-15",
    plate_format: "384",
    plate_count: 1,
    notes: null,
    qc_metrics: null,
    lock_reason: null,
    is_locked: false,
    status: "approved",
    targets: [],
    collections: [],
    ...over,
  }) as Run;

describe("RunSummaryCard facts band", () => {
  it("renders the protocol link, run date, plate format label, and plate count", () => {
    render(<RunSummaryCard run={run()} protocol={undefined} canEditMeta canEditTags />);
    expect(screen.getByText("p1")).toBeInTheDocument();
    expect(screen.getByText("2026-05-15")).toBeInTheDocument();
    expect(screen.getByText("384-Well")).toBeInTheDocument();
    expect(screen.getByText("1 plate")).toBeInTheDocument();
  });

  it("pluralizes the plate count", () => {
    render(
      <RunSummaryCard run={run({ plate_count: 3 })} protocol={undefined} canEditMeta canEditTags />,
    );
    expect(screen.getByText("3 plates")).toBeInTheDocument();
  });

  it("shows a color-coded Z' chip linking to #qc when QC data is present", () => {
    render(
      <RunSummaryCard
        run={run({ qc_metrics: { z_prime: 0.82 } })}
        protocol={undefined}
        canEditMeta
        canEditTags
      />,
    );
    const chip = screen.getByRole("link", { name: /Excellent/ });
    expect(chip).toHaveAttribute("href", "#qc");
    expect(chip.textContent).toContain("0.82");
  });

  it("classifies a poor Z' worst-plate value", () => {
    render(
      <RunSummaryCard
        run={run({
          qc_metrics: { z_prime: { "plate-1": { z_prime: 0.7 }, "plate-2": { z_prime: -0.2 } } },
        })}
        protocol={undefined}
        canEditMeta
        canEditTags
      />,
    );
    // Worst across plates is -0.2 → Poor.
    expect(screen.getByText(/Poor/)).toBeInTheDocument();
  });

  it("hides the Z' chip entirely when there is no QC data", () => {
    render(
      <RunSummaryCard
        run={run({ qc_metrics: null })}
        protocol={undefined}
        canEditMeta
        canEditTags
      />,
    );
    expect(screen.queryByText(/Excellent|Marginal|Poor/)).not.toBeInTheDocument();
  });

  it("surfaces the lock reason when the run is locked", () => {
    render(
      <RunSummaryCard
        run={run({ is_locked: true, lock_reason: "FDA submission window" })}
        protocol={undefined}
        canEditMeta={false}
        canEditTags
      />,
    );
    expect(screen.getByText(/FDA submission window/)).toBeInTheDocument();
  });
});
