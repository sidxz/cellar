import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { CampaignResponse } from "../../types";
import { LibrariesSection } from "./libraries-section";

const { addMutate, removeMutate, coverage } = vi.hoisted(() => ({
  addMutate: vi.fn(async () => undefined),
  removeMutate: vi.fn(async () => undefined),
  coverage: vi.fn(),
}));

vi.mock("../../hooks/use-campaign-collections", () => ({
  useCampaignCollectionCoverage: () => coverage(),
  useAddCampaignCollection: () => ({ mutateAsync: addMutate, isPending: false }),
  useRemoveCampaignCollection: () => ({ mutateAsync: removeMutate, isPending: false }),
  invalidateCampaignCollectionQueries: vi.fn(async () => undefined),
}));

// The picker itself is covered by its own tests; here it only has to hand the
// section a new id set so the add/remove diff is what's under test.
vi.mock("@/features/screening-assay/components/collection-multi-select", () => ({
  CollectionMultiSelect: ({ onChange }: { onChange: (ids: string[]) => void }) => (
    <button type="button" onClick={() => onChange(["lib-2"])}>
      pick lib-2 only
    </button>
  ),
}));

const campaign = {
  id: "camp-1",
  name: "Round 1",
  project_id: "proj-1",
  status: "draft",
  seed_runs: [{ run_id: "run-1", protocol_id: "proto-1" }],
  stages: [
    { id: "stage-1", name: "Primary" },
    { id: "stage-2", name: "Confirm" },
  ],
} as unknown as CampaignResponse;

/** tally_stage_counts' buckets: population = hit + miss + untested + pending. */
function stageCounts(
  stage_id: string,
  over: Partial<Record<string, number>> = {},
): Record<string, unknown> {
  return {
    stage_id,
    counts: {
      population: 0,
      hit: 0,
      miss: 0,
      untested: 0,
      pending: 0,
      not_in_stage: 0,
      overridden: 0,
      ...over,
    },
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderSection(props: { readOnly?: boolean; campaign?: CampaignResponse } = {}) {
  return render(
    <LibrariesSection campaign={props.campaign ?? campaign} readOnly={props.readOnly ?? false} />,
    { wrapper },
  );
}

// Radix Popover drives pointer capture APIs jsdom does not ship.
beforeAll(() => {
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
  Element.prototype.scrollIntoView ??= vi.fn();
});

beforeEach(() => {
  vi.clearAllMocks();
  coverage.mockReturnValue({
    data: [
      {
        id: "lib-1",
        name: "Diversity 5k",
        type: "library",
        covered: 3,
        total: 4,
        fraction: 0.75,
        stages: [
          // 3 rows reached Primary, one of them untested there: 2 hits / 2 tested.
          stageCounts("stage-1", { population: 3, hit: 2, miss: 0, untested: 1 }),
          stageCounts("stage-2", { population: 2, hit: 1, miss: 1 }),
        ],
      },
      {
        id: "lib-2",
        name: "Kinase focused",
        type: "library",
        covered: 0,
        total: 2,
        fraction: 0,
        stages: [stageCounts("stage-1"), stageCounts("stage-2")],
      },
    ],
    isLoading: false,
  });
});

describe("LibrariesSection", () => {
  it("shows a coverage bar per linked library", () => {
    renderSection();
    expect(screen.getByText("Diversity 5k")).toBeInTheDocument();
    expect(screen.getByText("3 / 4 · 75%")).toBeInTheDocument();
    expect(screen.getByText("Kinase focused")).toBeInTheDocument();
  });

  it("links and unlinks only what the picker changed", async () => {
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: /library/i }));
    fireEvent.click(await screen.findByText("pick lib-2 only"));

    // lib-2 was already linked, so only lib-1's removal should fire — an
    // idempotent re-add of lib-2 would be a wasted write.
    await waitFor(() => expect(removeMutate).toHaveBeenCalledWith("lib-1"));
    expect(addMutate).not.toHaveBeenCalled();
  });

  it("shows hits and tested per stage, by stage name", () => {
    renderSection();
    expect(screen.getAllByText("Primary")).toHaveLength(2);
    expect(screen.getByText("2 hits / 2 tested")).toBeInTheDocument();
    expect(screen.getByText("1 hit / 2 tested")).toBeInTheDocument();
    // A library that reached no stage still lists them, at zero.
    expect(screen.getAllByText("0 hits / 0 tested")).toHaveLength(2);
  });

  it("says nothing was screened when the campaign has no seed runs", () => {
    renderSection({ campaign: { ...campaign, seed_runs: [] } as CampaignResponse });
    expect(screen.getByText(/not built from runs/i)).toBeInTheDocument();
  });

  it("hides the picker on a closed campaign", () => {
    renderSection({ readOnly: true });
    expect(screen.queryByRole("button", { name: /library/i })).not.toBeInTheDocument();
  });

  it("invites the first library when none are linked", () => {
    coverage.mockReturnValue({ data: [], isLoading: false });
    renderSection();
    expect(screen.getByText(/No libraries yet/i)).toBeInTheDocument();
  });
});
