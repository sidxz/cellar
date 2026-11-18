import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { CampaignStageResponse } from "../types";
import { AddFromRunsDialog } from "./add-from-runs-dialog";

const { previewMutate, addMutate } = vi.hoisted(() => ({
  previewMutate: vi.fn(),
  addMutate: vi.fn(),
}));

vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  usePreviewRunImportApiV1CampaignsCampaignIdPreviewRunImportPost: () => ({
    mutate: previewMutate,
    isPending: false,
  }),
  useAddResultsFromRunsApiV1CampaignsCampaignIdAddFromRunsPost: () => ({
    mutate: addMutate,
    isPending: false,
  }),
}));

vi.mock("@/shared/lib/api/runs/runs", () => ({
  useListRunsByProtocolApiV1ProtocolsProtocolIdRunsGet: () => ({
    data: [{ id: "run-1", run_date: "2026-11-12", status: "approved", molecule_count: 3 }],
  }),
}));

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: () => ({ data: [{ id: "proto-1", name: "Kinase Panel" }] }),
  useProtocol: () => ({
    data: {
      id: "proto-1",
      name: "Kinase Panel",
      recommended_hit_criteria: [],
      readout_definitions: [{ id: "rd-1", name: "% Inhibition", data_type: "numeric" }],
    },
  }),
}));

// Radix Select portals a listbox whose items call scrollIntoView +
// hasPointerCapture — jsdom ships neither.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const PREVIEW = {
  summary: {
    runs: 1,
    channels_new: 1,
    channels_reused: 0,
    molecules_total: 1,
    hits: 1,
    non_hits: 0,
    molecules_already_in_campaign: 0,
  },
  rows: [],
  channels: [],
};

beforeEach(() => {
  addMutate.mockClear();
  previewMutate.mockReset();
  previewMutate.mockImplementation((_vars, opts) => opts?.onSuccess?.(PREVIEW));
});

const primary = {
  id: "st-1",
  name: "Primary",
  display_order: 0,
  kind: "criteria",
  criteria: [],
} as unknown as CampaignStageResponse;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function pick(trigger: HTMLElement, optionText: string | RegExp) {
  fireEvent.click(trigger);
  fireEvent.click(within(screen.getByRole("listbox")).getByText(optionText));
}

function chooseProtocolAndRun() {
  pick(screen.getByRole("combobox", { name: "Protocol" }), "Kinase Panel");
  fireEvent.click(screen.getByRole("checkbox", { name: /Run on/ }));
}

describe("AddFromRunsDialog stage", () => {
  it("blocks the preview until a stage is picked when the campaign has stages", async () => {
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    expect(screen.getByRole("button", { name: /^Preview/ })).toBeDisabled();

    pick(screen.getByRole("combobox", { name: "Stage" }), "Primary");
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));

    // The preview and the commit name the same stage.
    await waitFor(() => expect(previewMutate).toHaveBeenCalled());
    expect(previewMutate.mock.calls[0][0].data.stage_id).toBe("st-1");
    fireEvent.click(await screen.findByRole("button", { name: "Add 1 hit to Primary" }));
    expect(addMutate.mock.calls[0][0].data).toMatchObject({ stage_id: "st-1", stage_name: null });
  });

  it("starts on the stage it was opened from", async () => {
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        initialStageId="st-1"
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));
    await waitFor(() => expect(previewMutate).toHaveBeenCalled());
    expect(previewMutate.mock.calls[0][0].data.stage_id).toBe("st-1");
  });

  it("sends no stage for Other columns", async () => {
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    pick(screen.getByRole("combobox", { name: "Stage" }), /^Other columns/);
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Add 1 hit" }));
    expect(addMutate.mock.calls[0][0].data).toMatchObject({ stage_id: null, stage_name: null });
  });

  it("previews a new stage with the same name and parent the commit sends", async () => {
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    pick(screen.getByRole("combobox", { name: "Stage" }), "New stage…");
    pick(screen.getByRole("combobox", { name: "Parent stage" }), "Primary");
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));

    await waitFor(() => expect(previewMutate).toHaveBeenCalled());
    const previewed = previewMutate.mock.calls[0][0].data;
    expect(previewed).toMatchObject({
      stage_id: null,
      stage_name: "Kinase Panel hits",
      parent_stage_id: "st-1",
    });
    fireEvent.click(await screen.findByRole("button", { name: "Add 1 hit to Kinase Panel hits" }));
    expect(addMutate.mock.calls[0][0].data).toEqual({ ...previewed, scope: "hits_only" });
  });

  it("commits only a successful preview of what is picked now", async () => {
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        initialStageId="st-1"
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));
    expect(await screen.findByRole("button", { name: "Add 1 hit to Primary" })).toBeEnabled();

    // Back, change the stage, preview again: Primary's preview no longer counts.
    let resolveSecond: (() => void) | undefined;
    previewMutate.mockImplementation((_vars, opts) => {
      resolveSecond = () => opts?.onSuccess?.(PREVIEW);
    });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    pick(screen.getByRole("combobox", { name: "Stage" }), /^Other columns/);
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));
    expect(screen.getByRole("button", { name: /^Add/ })).toBeDisabled();
    await waitFor(() => expect(previewMutate).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: /^Add/ })).toBeDisabled();

    act(() => resolveSecond?.());
    expect(screen.getByRole("button", { name: "Add 1 hit" })).toBeEnabled();
  });

  it("never commits after a failed preview", async () => {
    previewMutate.mockImplementation((_vars, opts) => opts?.onError?.(new Error("boom")));
    render(
      <AddFromRunsDialog
        campaignId="c1"
        projectId="p1"
        stages={[primary]}
        initialStageId="st-1"
        open
        onOpenChange={vi.fn()}
      />,
      { wrapper },
    );
    chooseProtocolAndRun();
    fireEvent.click(screen.getByRole("button", { name: /^Preview/ }));
    expect(await screen.findByText(/The preview failed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Add/ })).toBeDisabled();
  });
});
