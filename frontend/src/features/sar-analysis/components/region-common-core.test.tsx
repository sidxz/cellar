import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { McsResult, UseMcsReturn } from "../hooks/use-mcs";

const PYRIDINE = "c1ccncc1";

const m = vi.hoisted(() => ({
  ret: { mcs: null, isLoading: false, error: null, outOfRange: false } as UseMcsReturn,
}));

vi.mock("../hooks/use-mcs", () => ({
  useMcs: (): UseMcsReturn => m.ret,
}));

vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <div data-testid={`thumb-${smiles}`} />,
}));

import { RegionCommonCore } from "./region-common-core";

function setMcs(mcs: Partial<McsResult> | null, rest: Partial<UseMcsReturn> = {}) {
  m.ret = {
    mcs: mcs
      ? {
          smarts: "[#6]1:[#6]:[#6]:[#7]:[#6]:[#6]:1",
          core_smiles: PYRIDINE,
          num_atoms: 6,
          num_bonds: 6,
          timed_out: false,
          molecule_count: 12,
          ...mcs,
        }
      : null,
    isLoading: false,
    error: null,
    outOfRange: false,
    ...rest,
  };
}

function open(regionIds: string[], onUseAsCore = vi.fn()) {
  render(<RegionCommonCore regionIds={regionIds} onUseAsCore={onUseAsCore} />);
  fireEvent.click(screen.getByRole("button", { name: /Common core/i }));
  return onUseAsCore;
}

const REGION = Array.from({ length: 12 }, (_, i) => `m${i}`);

describe("<RegionCommonCore />", () => {
  it("shows the shared core and hands it to the R-group workbench", () => {
    setMcs({ num_atoms: 22, molecule_count: 12 });
    const onUseAsCore = open(REGION);

    expect(screen.getByTestId(`thumb-${PYRIDINE}`)).toBeInTheDocument();
    expect(screen.getByText(/Shared by all 12/)).toBeInTheDocument();
    expect(screen.getByText(/22 atoms/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Use as R-group core/i }));
    expect(onUseAsCore).toHaveBeenCalledWith(PYRIDINE, REGION);
  });

  it("reports a region that shares nothing, rather than treating it as a failure", () => {
    // Informational surface: "these span more than one chemotype" is a useful
    // answer about the lasso, not an error.
    setMcs({ core_smiles: null, num_atoms: 0, num_bonds: 0 });
    open(REGION);

    expect(screen.getByText(/share no common substructure/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Use as R-group core/i })).not.toBeInTheDocument();
  });

  it("marks a timed-out answer partial and refuses to seed a core with it", () => {
    setMcs({ timed_out: true, num_atoms: 18 });
    open(REGION);

    expect(screen.getByText(/Partial/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Use as R-group core/i })).toBeDisabled();
  });

  it("needs at least two compounds before it will ask", () => {
    setMcs(null);
    render(<RegionCommonCore regionIds={["only-one"]} onUseAsCore={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Common core/i })).toBeDisabled();
  });

  it("says so plainly when the selection is outside the sizes the endpoint takes", () => {
    setMcs(null, { outOfRange: true });
    open(REGION);

    expect(screen.getByText(/between 2 and 10,000 compounds/i)).toBeInTheDocument();
  });
});
