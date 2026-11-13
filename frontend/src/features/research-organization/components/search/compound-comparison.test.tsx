import type { Molecule } from "@/features/chemical-registration/types";
import { CompoundCurvesProvider } from "@/features/screening-assay/components/compound-curves-dialog";
import type { Protocol } from "@/features/screening-assay/types";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { ActivityValue } from "../../types";
import { CompoundComparison } from "./compound-comparison";

const curvesProps = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock("@/features/screening-assay/components/multi-run-curves", () => ({
  MultiRunCurves: (props: Record<string, unknown>) => {
    curvesProps.push(props);
    return <div data-testid="multi-run-curves" />;
  },
}));

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
});

const av: ActivityValue = {
  value: 100,
  qualifier: "=",
  unit: "nM",
  source: "dose_response",
  curve_type: "ic50",
  r_squared: 0.99,
  data_point_count: 8,
  raw_data: null,
  curve_params: null,
};
const protocols = ["Target", "Counter"].map((name) => ({
  id: name,
  name,
  readout_definitions: [
    {
      id: name,
      name: "Potency",
      dose_response_config: {
        intercepts: [
          { kind: "ic", level: 50, basis: "relative_percent" },
          { kind: "ic", level: 90, basis: "relative_percent" },
        ],
      },
    },
  ],
})) as unknown as Protocol[];
const molecules = ["A", "B"].map((id) => ({
  id,
  name: id,
  activity: {
    "drc:Target": av,
    "drc:Counter": { ...av, value: 2, unit: "uM", qualifier: id === "A" ? "=" : ">" },
  },
})) as unknown as (Molecule & { activity: Record<string, ActivityValue> })[];

const third = { ...molecules[0], id: "C", name: "C" };
const allMolecules = [...molecules, third];
function Harness({ save = () => {} }: { save?: (ids: string[]) => void }) {
  const [ids, setIds] = useState(["A", "B"]);
  const [pair, setPair] = useState({ targetId: "", counterId: "" });
  const [open, setOpen] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Reopen comparison
      </button>
      <CompoundComparison
        molecules={ids.flatMap((id) => allMolecules.filter((mol) => mol.id === id))}
        availableMolecules={allMolecules}
        onMoleculesChange={setIds}
        endpointPair={pair}
        onEndpointPairChange={setPair}
        onSaveShortlist={() => save(ids)}
        open={open}
        protocols={protocols}
        protocolColumns={["drc:Target", "drc:Counter"]}
        mode="latest"
        onClose={() => setOpen(false)}
      />
    </>
  );
}
function setup(save?: (ids: string[]) => void) {
  render(<Harness save={save} />);
  fireEvent.change(screen.getByLabelText("Target assay"), {
    target: { value: "drc:Target:ic:50" },
  });
}

describe("compound comparison", () => {
  it("calculates a ratio for an exact pair and explains a qualified pair", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Counter assay"), {
      target: { value: "drc:Counter:ic:50" },
    });
    expect(screen.getByText("20.0×")).toBeInTheDocument();
    expect(screen.getByText("Requires two positive, unqualified endpoints")).toBeInTheDocument();
  });
  it("does not compare mismatched endpoint levels", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Counter assay"), {
      target: { value: "drc:Counter:ic:90" },
    });
    expect(screen.getAllByText("Choose matching endpoint types and levels")).toHaveLength(2);
    expect(screen.queryByText("20.0×")).not.toBeInTheDocument();
  });
});

it("keeps endpoint choices while replacing, removing, adding and reopening compounds", async () => {
  const save = vi.fn();
  setup(save);
  fireEvent.change(screen.getByLabelText("Counter assay"), {
    target: { value: "drc:Counter:ic:50" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Replace A" }));
  fireEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: /C/ }));
  expect(screen.getByRole("button", { name: "Replace C" })).toBeInTheDocument();
  expect(screen.getByLabelText("Target assay")).toHaveValue("drc:Target:ic:50");
  expect(screen.getByLabelText("Counter assay")).toHaveValue("drc:Counter:ic:50");
  fireEvent.click(screen.getByRole("button", { name: "Remove B from comparison" }));
  expect(screen.getByRole("dialog", { name: "Compare 1 compound" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add compound" }));
  fireEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: /A/ }));
  fireEvent.click(screen.getByRole("button", { name: "Save shortlist (2)" }));
  expect(save).toHaveBeenCalledWith(["C", "A"]);
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  fireEvent.click(screen.getByRole("button", { name: "Reopen comparison" }));
  expect(screen.getByLabelText("Target assay")).toHaveValue("drc:Target:ic:50");
  expect(screen.getByLabelText("Counter assay")).toHaveValue("drc:Counter:ic:50");
  fireEvent.click(screen.getByRole("button", { name: "Remove C from comparison" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove A from comparison" }));
  expect(screen.getByRole("dialog", { name: "Compare compounds" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save shortlist (0)" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Add compound" })).toBeEnabled();
});

it("Curves on a protocol opens the curves of all compared compounds, once per protocol", () => {
  render(
    <CompoundCurvesProvider>
      <CompoundComparison
        molecules={molecules}
        availableMolecules={allMolecules}
        onMoleculesChange={() => {}}
        endpointPair={{ targetId: "", counterId: "" }}
        onEndpointPairChange={() => {}}
        onSaveShortlist={() => {}}
        protocols={[{ ...protocols[0], has_measured_curves: true }, protocols[1]]}
        protocolColumns={["drc:Target", "drc:Counter"]}
        mode="latest"
        onClose={() => {}}
      />
    </CompoundCurvesProvider>,
  );
  // Target has two endpoint rows and curves; Counter has none.
  const buttons = screen.getAllByRole("button", { name: "Traces" });
  expect(buttons).toHaveLength(1);
  fireEvent.click(buttons[0]);
  expect(
    screen.getByRole("dialog", { name: "Traces across runs", description: /^Target · A and B\./ }),
  ).toBeInTheDocument();
  expect(curvesProps.at(-1)?.protocolId).toBe("Target");
  expect(curvesProps.at(-1)?.filter).toEqual({ moleculeIds: ["A", "B"] });
});
