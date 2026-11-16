import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { provenanceOf } from "../lib/traces/test-fixtures";
import type { Dataset, DatasetColumn, DatasetSource, Level } from "../types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const R1 = "11111111-1111-4111-8111-111111111111";
const R2 = "22222222-2222-4222-8222-222222222222";
const R3 = "33333333-3333-4333-8333-333333333333";
const B1 = "44444444-4444-4444-8444-444444444444";
const B2 = "55555555-5555-4555-8555-555555555555";
const U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const P1 = "99999999-9999-4999-8999-999999999999";
const P2 = "88888888-8888-4888-8888-888888888888";
const run = (protocol_id: string) => (r: { id: string; run_date: string }) => ({
  ...r,
  status: "approved",
  conditions: null,
  created_at: "1",
  operator: U1,
  plate_count: 1,
  protocol_id,
});
const runsA = [
  { id: R1, run_date: "2026-11-12" },
  { id: R2, run_date: "2026-11-05" },
  { id: R3, run_date: "2026-10-29" },
].map(run(P1));
const runsB = [
  { id: B1, run_date: "2026-09-08" },
  { id: B2, run_date: "2026-09-01" },
].map(run(P2));
const protocols = [
  { id: P1, name: "NadD HTS", status: "published", protocol_type: "x", run_count: 3 },
  { id: P2, name: "MMP2 counter", status: "published", protocol_type: "x", run_count: 2 },
];

const state = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  replace: vi.fn(),
  protocolReads: 0,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => (id === U1 ? "A. Chen" : ""),
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: (id?: string) => ({ data: id === P2 ? runsB : runsA, isLoading: false }),
  useRun: (id: string) => ({ data: runsA.find((r) => r.id === id) }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: (id?: string) => {
    state.protocolReads += 1;
    return { data: protocols.find((p) => p.id === id) };
  },
  useProtocolSummaries: () => ({ data: protocols, isLoading: false }),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../hooks/use-dataset", () => ({ useDataset: () => state.query }));
vi.mock("../hooks/use-run-row-counts", () => ({ useRunRowCounts: () => ({ data: undefined }) }));

import { WorkbenchPage } from "./workbench-page";

const col = (key: string, kind: DatasetColumn["kind"], hidden = false): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: provenanceOf(key),
  hidden,
});

/** Compounds of NadD HTS joined with MMP2 counter: m1 and m3 tested there, m2 not. */
function crossed(): Dataset {
  return {
    revision: "rev-x",
    level: "compounds",
    row_count: 3,
    row_ids: ["m1", "m2", "m3"],
    protocols: [
      { protocol_id: P1, name: "NadD HTS" },
      { protocol_id: P2, name: "MMP2 counter" },
    ],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("rd:s:raw", "number"),
      {
        key: `tested:${P2}`,
        label: "Tested in MMP2 counter",
        kind: "category",
        group: "MMP2 counter",
        provenance: { protocol_id: P2 },
      },
      {
        key: "rd:b:raw",
        label: "MMP2 counter · b",
        kind: "number",
        group: "MMP2 counter",
        provenance: { protocol_id: P2, readout_definition_id: "b" },
      },
    ],
    values: {
      compound: ["CEL-1", "CEL-2", "CEL-3"],
      molecule_id: ["m1", "m2", "m3"],
      "rd:s:raw": [1, 2, 3],
      [`tested:${P2}`]: ["Tested", "Not tested", "Tested"],
      "rd:b:raw": [5, null, null],
    },
  };
}

/** NadD HTS alone at Compounds: m1 and m2. */
function single(): Dataset {
  return {
    revision: "rev-1",
    level: "compounds",
    row_count: 2,
    row_ids: ["m1", "m2"],
    protocols: [{ protocol_id: P1, name: "NadD HTS" }],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("rd:s:raw", "number"),
    ],
    values: { compound: ["CEL-1", "CEL-2"], molecule_id: ["m1", "m2"], "rd:s:raw": [1, 2] },
  };
}

const ready = (ds: Dataset) => ({ data: ds, isPending: false, isError: false, refetch: vi.fn() });

const client = new QueryClient();
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);
const page = (level: Level, source: DatasetSource) =>
  render(<WorkbenchPage level={level} source={source} />, { wrapper });

// Radix Popover / cmdk need these in jsdom.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

beforeEach(() => {
  state.replace.mockReset();
  state.query = ready(crossed());
});

const compared: DatasetSource = {
  kind: "protocol",
  protocolId: P1,
  compare: [{ protocolId: P2, runIds: [B1] }],
};

describe("WorkbenchHeader comparing protocols", () => {
  it("names each compared protocol with its runs and tested compounds; ✕ removes it", () => {
    page("compounds", compared);
    expect(
      screen.getByRole("button", { name: "MMP2 counter · 1 of 2 runs · 2 of 3 compounds tested" }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
    fireEvent.click(screen.getByRole("button", { name: "Remove MMP2 counter" }));
    expect(state.replace).toHaveBeenCalledWith(`/assays/visualize?protocol=${P1}&level=compounds`, {
      scroll: false,
    });
  });

  it("offers Add protocol at Compounds only, never for a run, and up to five protocols", () => {
    state.query = ready({ ...single(), level: "wells" });
    page("wells", { kind: "protocol", protocolId: P1 });
    const add = screen.getByRole("button", { name: "Add protocol" });
    // Unavailable but reachable by keyboard, so its reason can be read.
    expect(add).toHaveAttribute("aria-disabled", "true");
    expect(add).toBeEnabled();
    expect(add).toHaveAccessibleDescription("Switch to Compounds to compare protocols");
    fireEvent.click(add);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    cleanup();

    page("wells", { kind: "run", runId: R1 });
    expect(screen.queryByRole("button", { name: "Add protocol" })).not.toBeInTheDocument();
    cleanup();

    state.query = ready(crossed());
    const four = ["a", "b", "c", "d"].map((protocolId) => ({ protocolId }));
    page("compounds", { kind: "protocol", protocolId: P1, compare: four });
    expect(screen.getByRole("button", { name: "Add protocol" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("button", { name: "Add protocol" })).toHaveAccessibleDescription(
      "Up to 5 protocols",
    );
  });

  it("keeps the level at Compounds while protocols are compared, saying why", () => {
    page("compounds", compared);
    for (const name of ["Wells", "Runs", "Batches"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).toBeEnabled();
      expect(button).toHaveAccessibleDescription(
        "Comparing protocols works at the Compounds level only — remove the added protocols to switch.",
      );
      fireEvent.click(button);
    }
    expect(state.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Compounds" })).toBeEnabled();
  });

  it("keeps only compounds tested in both, in one undo step", () => {
    page("compounds", compared);
    const toggle = screen.getByRole("switch", { name: "Only compounds tested in both" });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(toggle).toBeChecked();
    expect(screen.getByText("2 / 3 compounds")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tested in MMP2 counter" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(toggle).not.toBeChecked();
    expect(screen.getByText("3 / 3 compounds")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Redo" }));
    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(screen.queryByRole("group", { name: "Tested in MMP2 counter" })).not.toBeInTheDocument();
  });

  it("names the protocol count once more than two are loaded", () => {
    const ds = crossed();
    state.query = ready({
      ...ds,
      protocols: [...(ds.protocols ?? []), { protocol_id: "p3", name: "Third" }],
    });
    page("compounds", compared);
    expect(
      screen.getByRole("switch", { name: "Only compounds tested in all 3 protocols" }),
    ).toBeInTheDocument();
  });

  it("adding a protocol keeps the filters and the selected compounds", async () => {
    const alone: DatasetSource = { kind: "protocol", protocolId: P1 };
    state.query = ready(single());
    const { rerender } = page("compounds", alone);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    fireEvent.click((await screen.findAllByRole("checkbox", { name: "Select row" }))[0]);

    fireEvent.click(screen.getByRole("button", { name: "Add protocol" }));
    expect(screen.queryByRole("option", { name: /NadD HTS/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: /MMP2 counter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add protocol" }));
    expect(state.replace).toHaveBeenCalledWith(
      `/assays/visualize?protocol=${P1}&compare=${P2}&level=compounds`,
      { scroll: false },
    );

    state.query = ready(crossed());
    rerender(
      <WorkbenchPage level="compounds" source={{ ...alone, compare: [{ protocolId: P2 }] }} />,
    );
    expect(screen.getByRole("group", { name: "rd:s:raw" })).toBeInTheDocument();
    expect(screen.getByText(/selected ·/).textContent).toMatch(/^1 compound selected/);
    // No note: the level is the same and nothing was lost.
    expect(document.querySelector("output")).toHaveTextContent(/^$/);
  });

  it("removing a protocol names what went with it and keeps the selection", async () => {
    const { rerender } = page("compounds", compared);
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "MMP2 counter · b" }));
    fireEvent.click((await screen.findAllByRole("checkbox", { name: "Select row" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Remove MMP2 counter" }));

    state.query = ready(single());
    rerender(<WorkbenchPage level="compounds" source={{ kind: "protocol", protocolId: P1 }} />);
    expect(document.querySelector("output")).toHaveTextContent(
      "Not available now: Filter: MMP2 counter · b.",
    );
    expect(screen.getByText(/selected ·/).textContent).toMatch(/^1 compound selected/);
  });

  it("gives focus back to Add protocol when it closes without adding", async () => {
    state.query = ready(single());
    page("compounds", { kind: "protocol", protocolId: P1 });
    const add = screen.getByRole("button", { name: "Add protocol" });
    add.focus();
    fireEvent.click(add);
    // Picking a protocol swaps in its run picker; cancelling that still returns focus.
    fireEvent.click(screen.getByRole("option", { name: /MMP2 counter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(add).toHaveFocus());
  });

  it("selecting rows leaves the header as it is", async () => {
    page("compounds", compared);
    const boxes = await screen.findAllByRole("checkbox", { name: "Select row" });
    const before = state.protocolReads;
    fireEvent.click(boxes[0]);
    expect(screen.getByText(/selected ·/).textContent).toMatch(/^1 compound selected/);
    expect(state.protocolReads).toBe(before);
  });

  it("changing runs from a run's workbench keeps its filters", async () => {
    state.query = ready({ ...single(), level: "runs" });
    const { rerender } = page("runs", { kind: "run", runId: R1 });
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    fireEvent.click(screen.getByRole("button", { name: /^NadD HTS · run 2026-11-12/ }));
    fireEvent.click(screen.getByRole("button", { name: "Change runs…" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Include 2026-11-05 · A. Chen" }));
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(state.replace).toHaveBeenLastCalledWith(
      `/assays/visualize?protocol=${P1}&runs=${R1}%2C${R2}&level=runs`,
      { scroll: false },
    );

    rerender(
      <WorkbenchPage
        level="runs"
        source={{ kind: "protocol", protocolId: P1, runIds: [R1, R2] }}
      />,
    );
    expect(screen.getByRole("group", { name: "rd:s:raw" })).toBeInTheDocument();
  });

  it("changing runs keeps the compared protocols", () => {
    page("compounds", compared);
    fireEvent.click(screen.getByRole("button", { name: /^NadD HTS · 3 of 3 runs/ }));
    fireEvent.click(screen.getByRole("button", { name: "Change runs…" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Include 2026-10-29 · A. Chen" }));
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(state.replace).toHaveBeenLastCalledWith(
      `/assays/visualize?protocol=${P1}&runs=${R1}%2C${R2}&compare=${P2}%3A${B1}&level=compounds`,
      { scroll: false },
    );

    fireEvent.click(screen.getByRole("button", { name: /^MMP2 counter · 1 of 2 runs/ }));
    fireEvent.click(screen.getByRole("button", { name: "Change runs…" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Include all runs" }));
    fireEvent.click(screen.getByRole("button", { name: "Open workbench" }));
    expect(state.replace).toHaveBeenLastCalledWith(
      `/assays/visualize?protocol=${P1}&compare=${P2}&level=compounds`,
      { scroll: false },
    );
  });
});
