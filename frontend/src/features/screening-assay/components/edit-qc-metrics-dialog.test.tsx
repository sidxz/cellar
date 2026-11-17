import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mutate = vi.fn();
vi.mock("../hooks/use-runs", () => ({ useUpdateRun: () => ({ mutate, isPending: false }) }));

import type { Run } from "../types";
import { EditQcMetricsDialog } from "./edit-qc-metrics-dialog";

describe("EditQcMetricsDialog", () => {
  it("edits the scalar metrics and keeps the computed plate QC as it is", () => {
    const computed = {
      z_prime: { pl1: { z_prime: 0.9, classification: "excellent" } },
      plates: { pl1: { rd1: { raw: { z_prime: 0.9 } } } },
    };
    const run = { id: "r1", qc_metrics: { ...computed, cv_percent: 3.2 } } as unknown as Run;
    render(<EditQcMetricsDialog run={run} open onOpenChange={() => {}} />);

    expect(screen.getAllByPlaceholderText("Key").map((i) => (i as HTMLInputElement).value)).toEqual(
      ["cv_percent"],
    );
    fireEvent.click(screen.getByRole("button", { name: "Save Metrics" }));

    expect(mutate.mock.calls[0][0]).toEqual({
      runId: "r1",
      data: { qc_metrics: { ...computed, cv_percent: 3.2 } },
    });
  });
});
