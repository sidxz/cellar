import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// CardGrid virtualizes (heavy in jsdom) — stub it to a simple count.
vi.mock("@/features/research-organization/components/results/card-grid", () => ({
  CardGrid: ({ molecules }: any) => (
    <div data-testid="card-grid">cards:{molecules.length}</div>
  ),
}));

import { ClusterSelectionPane } from "./cluster-selection-pane";

const molecules: any[] = [
  { id: "a", name: "A" },
  { id: "b", name: "B" },
  { id: "c", name: "C" },
];

describe("ClusterSelectionPane", () => {
  it("shows an empty hint when the basket is empty", () => {
    render(
      <ClusterSelectionPane allMolecules={molecules} basketIds={new Set()} />,
    );
    expect(screen.getByText(/basket is empty/i)).toBeInTheDocument();
    expect(screen.queryByTestId("card-grid")).not.toBeInTheDocument();
  });

  it("shows the basket count and cards when non-empty", () => {
    render(
      <ClusterSelectionPane
        allMolecules={molecules}
        basketIds={new Set(["a", "c"])}
      />,
    );
    expect(screen.getByText(/basket \(2\)/i)).toBeInTheDocument();
    expect(screen.getByTestId("card-grid")).toHaveTextContent("cards:2");
  });
});
