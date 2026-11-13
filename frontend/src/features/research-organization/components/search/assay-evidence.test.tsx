import { CompoundCurvesProvider } from "@/features/screening-assay/components/compound-curves-dialog";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ActivityValue } from "../../types";
import { AssayEvidence } from "./assay-evidence";

const curvesProps: Array<Record<string, unknown>> = [];
vi.mock("@/features/screening-assay/components/multi-run-curves", () => ({
  MultiRunCurves: (props: Record<string, unknown>) => {
    curvesProps.push(props);
    return <div data-testid="multi-run-curves" />;
  },
}));

const av: ActivityValue = {
  value: 1.5,
  qualifier: "=",
  unit: "uM",
  source: "readout",
  curve_type: null,
  r_squared: null,
  data_point_count: 1,
  raw_data: null,
  curve_params: null,
};
const target = {
  protocol: { id: "p1", name: "Protocol 1" },
  molecules: [{ id: "m1", name: "ABC-0000001" }],
};

function renderEvidence(curves: typeof target | null) {
  const rowClick = vi.fn();
  render(
    <CompoundCurvesProvider>
      <div onClick={rowClick} onKeyDown={() => {}} role="presentation">
        <AssayEvidence av={av} mode="latest" curves={curves}>
          <span>1.5 uM</span>
        </AssayEvidence>
      </div>
    </CompoundCurvesProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /show run history/i }));
  return rowClick;
}

describe("<AssayEvidence /> curves", () => {
  it("offers Curves in the popover when a target is given, and opens the dialog", async () => {
    const rowClick = renderEvidence(target);
    expect(await screen.findByText(/Reported readout/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Traces" }));
    expect(
      await screen.findByRole("dialog", {
        name: "Traces across runs",
        description: /^Protocol 1 · ABC-0000001\./,
      }),
    ).toBeInTheDocument();
    expect(curvesProps.at(-1)?.filter).toEqual({ moleculeIds: ["m1"] });
    expect(rowClick).not.toHaveBeenCalled();
  });

  it("offers no Curves without a target", async () => {
    renderEvidence(null);
    expect(await screen.findByText(/Reported readout/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Traces" })).toBeNull();
  });

  it("offers no Curves outside a provider", async () => {
    render(
      <AssayEvidence av={av} mode="latest" curves={target}>
        <span>1.5 uM</span>
      </AssayEvidence>,
    );
    fireEvent.click(screen.getByRole("button", { name: /show run history/i }));
    expect(await screen.findByText(/Reported readout/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Traces" })).toBeNull();
  });
});
