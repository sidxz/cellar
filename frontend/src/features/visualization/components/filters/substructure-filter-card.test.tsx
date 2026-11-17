import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type Filter, type SubstructureFilter, membershipKey } from "../../lib/filters";
import { WorkbenchProvider, useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";

// What the mocked editor applies when its Apply button is clicked.
const drawn = vi.hoisted(() => ({ value: "c1ccncc1", format: "smiles" }));

// RDKit/Ketcher-free shim of the chemistry barrel.
vi.mock("@/shared/components/chemistry", () => ({
  StructureRenderer: ({ smiles, queryKind }: { smiles: string; queryKind: string }) => (
    <div data-testid="query-structure" data-smiles={smiles} data-kind={queryKind} />
  ),
  StructureEditorDialog: ({
    open,
    initialStructure,
    onApply,
  }: {
    open: boolean;
    initialStructure?: string;
    onApply: (s: string, f: string) => void;
  }) =>
    open ? (
      <button
        type="button"
        data-initial={initialStructure}
        onClick={() => onApply(drawn.value, drawn.format)}
      >
        Apply drawing
      </button>
    ) : null,
}));

vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { SubstructureFilterCard } from "./substructure-filter-card";

// m1 (2 wells) and m2 have structures, m3 has none; w3 is a control without a compound.
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 5,
  row_ids: ["w0", "w1", "w2", "w3", "w4"],
  columns: [
    { key: "structure", label: "Structure", kind: "structure", provenance: {} },
    { key: "molecule_id", label: "Molecule", kind: "text", provenance: {}, hidden: true },
  ],
  values: {
    structure: ["c1ccccc1C", "c1ccccc1C", "c1ccncc1", null, null],
    molecule_id: ["m1", "m1", "m2", null, "m3"],
  },
};

const benzene = (moleculeIds: string[]): SubstructureFilter => ({
  id: "sub-1",
  kind: "substructure",
  query: "c1ccccc1",
  queryKind: "smiles",
  moleculeIds,
  over: membershipKey(ds),
});

function Probe() {
  const filters = useWorkbench((s) => s.filters);
  const history = useWorkbench((s) => s.past.length);
  return <output data-testid="state">{JSON.stringify({ history, filters })}</output>;
}
const state = (): { history: number; filters: Filter[] } =>
  JSON.parse(screen.getByTestId("state").textContent ?? "{}");

function Card() {
  const filter = useWorkbench((s) => s.filters[0]);
  return filter?.kind === "substructure" ? (
    <SubstructureFilterCard ds={ds} filter={filter} active />
  ) : null;
}

const show = (filter: SubstructureFilter, data: Dataset = ds) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <WorkbenchProvider initialPanels={[]} initialFilters={[filter]}>
        {data === ds ? <Card /> : <SubstructureFilterCard ds={data} filter={filter} active />}
        <Probe />
      </WorkbenchProvider>
    </QueryClientProvider>,
  );

beforeEach(() => vi.mocked(customInstance).mockReset());

describe("SubstructureFilterCard", () => {
  it("draws the query, counts matching compounds and notes structureless compounds", () => {
    show(benzene(["m1"]));
    expect(screen.getByTestId("query-structure")).toHaveAttribute("data-smiles", "c1ccccc1");
    expect(screen.getByTestId("query-structure")).toHaveAttribute("data-kind", "smiles");
    expect(screen.getByText("1 of 3 compounds match")).toBeInTheDocument();
    expect(screen.getByText("1 compound has no structure and never matches")).toBeInTheDocument();
    expect(
      screen.getByText("Rows without a compound (controls, blanks) are hidden while this is on."),
    ).toBeInTheDocument();
  });

  it("warns when no compound contains the query", () => {
    show(benzene([]));
    expect(screen.getByText("No compounds contain this substructure")).toBeInTheDocument();
    expect(screen.queryByText(/compounds match/)).not.toBeInTheDocument();
  });

  it("leaves out the notes that do not apply", () => {
    const allDrawn: Dataset = {
      ...ds,
      row_count: 2,
      row_ids: ["c1", "c2"],
      values: { structure: ["c1ccccc1C", "c1ccncc1"], molecule_id: ["m1", "m2"] },
    };
    show({ ...benzene(["m1"]), over: membershipKey(allDrawn) }, allDrawn);
    expect(screen.getByText("1 of 2 compounds match")).toBeInTheDocument();
    expect(screen.queryByText(/no structure/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Rows without a compound/)).not.toBeInTheDocument();
  });

  it("titles the card Substructure, its count on a line of its own, the query on hover", () => {
    show(benzene(["m1"]));
    const header = screen.getByRole("button", { name: "Contains c1ccccc1" });
    expect(header).toHaveAttribute("title", "Contains c1ccccc1");
    const [title, count] = within(header).getByText("Substructure").parentElement?.children ?? [];
    expect(title).toHaveTextContent(/^Substructure$/);
    expect(count).toHaveTextContent(/^1 of 3 compounds$/);
    expect(title.parentElement).toHaveClass("flex-col");
  });

  it("collapses to its summary", () => {
    show(benzene(["m1"]));
    fireEvent.click(screen.getByRole("button", { name: "Contains c1ccccc1" }));
    expect(screen.queryByTestId("query-structure")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contains c1ccccc1" })).toHaveTextContent(
      "Substructure1 of 3 compounds",
    );
  });

  it("opened from a saved view: shows the query unmatched and matches it again on request", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce({
      matched_ids: ["m1"],
      searched: 3,
      without_structure: 1,
    });
    const { moleculeIds: _, ...saved } = benzene(["m9"]);
    show(saved);
    expect(screen.getByTestId("query-structure")).toHaveAttribute("data-smiles", "c1ccccc1");
    expect(
      screen.getByText("Not matched against this data yet — it filters nothing until matched."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/compounds match/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Match again" }));

    await waitFor(() => expect(state().filters).toEqual([benzene(["m1"])]));
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { query: "c1ccccc1", query_kind: "smiles", molecule_ids: ["m1", "m2", "m3"] },
      }),
    );
    expect(screen.getByText("1 of 3 compounds match")).toBeInTheDocument();
  });

  it("matches again by itself once the dataset's compounds change: no undo step, inert meanwhile", async () => {
    let answer: (body: unknown) => void = () => {};
    vi.mocked(customInstance).mockReturnValueOnce(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    // Matched over m1 and m2 only; m3 joined the dataset since.
    show({ ...benzene(["m1"]), over: "m1,m2" });
    expect(await screen.findByText("Matching…")).toBeInTheDocument();
    expect(screen.queryByText(/compounds match/)).not.toBeInTheDocument();
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { query: "c1ccccc1", query_kind: "smiles", molecule_ids: ["m1", "m2", "m3"] },
      }),
    );
    answer({ matched_ids: ["m1", "m3"], searched: 3, without_structure: 1 });
    await waitFor(() => expect(state().filters).toEqual([benzene(["m1", "m3"])]));
    expect(state().history).toBe(0);
    expect(await screen.findByText("2 of 3 compounds match")).toBeInTheDocument();
    expect(vi.mocked(customInstance)).toHaveBeenCalledTimes(1);
  });

  it("edits the query: re-matches and keeps the filter's id, in one undo step", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce({
      matched_ids: ["m2"],
      searched: 3,
      without_structure: 1,
    });
    show(benzene(["m1"]));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const apply = screen.getByRole("button", { name: "Apply drawing" });
    expect(apply).toHaveAttribute("data-initial", "c1ccccc1");
    fireEvent.click(apply);

    await waitFor(() => expect(state().history).toBe(1));
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/visualization/substructure-match",
        method: "POST",
        data: { query: "c1ccncc1", query_kind: "smiles", molecule_ids: ["m1", "m2", "m3"] },
      }),
    );
    expect(state()).toEqual({
      history: 1,
      filters: [{ ...benzene(["m2"]), query: "c1ccncc1" }],
    });
  });
});
