import { ApiError } from "@/shared/lib/api/custom-instance";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const refetch = vi.fn();
const mutateAsync = vi.fn();
let previewData: unknown;

vi.mock("@/shared/hooks/use-cascade-preview", () => ({
  useCascadePreview: () => ({
    data: previewData,
    isLoading: false,
    isSuccess: true,
    isError: false,
    refetch,
  }),
}));
vi.mock("@/shared/hooks/use-cascade-delete", () => ({
  useCascadeDelete: () => ({ mutateAsync, isPending: false }),
}));

import { CascadeDeleteDialog } from "./cascade-delete-dialog";

const root = {
  entity_type: "run",
  table: "runs",
  display_label: "run",
  count: 1,
  samples: [],
  truncated: false,
  action: "cascade",
  children: [],
};
const closedCampaign = {
  table: "campaign",
  entity_type: "campaign",
  fk_column: "campaign.seed_runs",
  count: 1,
  samples: [{ id: "c-1", label: "Kinase panel" }],
  truncated: false,
  display_label: "Closed or superseded campaigns citing this run",
};

function confirmWith(name: string) {
  fireEvent.change(screen.getByLabelText(/to confirm/i), { target: { value: name } });
  fireEvent.change(screen.getByPlaceholderText(/reason for deletion/i), {
    target: { value: "botched import" },
  });
}

function renderDialog() {
  render(
    <CascadeDeleteDialog
      entityType="run"
      entityId="r-1"
      entityLabel="Run 2026-09-15"
      open
      onOpenChange={vi.fn()}
    />,
  );
}

describe("CascadeDeleteDialog", () => {
  beforeEach(() => {
    refetch.mockReset();
    mutateAsync.mockReset();
  });

  it("lists blockers and keeps Force delete disabled while any exist", () => {
    previewData = { ...root, blockers: [closedCampaign], warnings: [] };
    renderDialog();
    confirmWith("Run 2026-09-15");

    expect(screen.getByText(/closed or superseded campaigns citing this run/i)).toBeInTheDocument();
    expect(screen.getByText(/kinase panel/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeDisabled();
  });

  it("lists warnings without blocking the delete", () => {
    previewData = {
      ...root,
      blockers: [],
      warnings: [{ ...closedCampaign, display_label: "Draft campaigns using this run" }],
    };
    renderDialog();
    confirmWith("Run 2026-09-15");

    expect(screen.getByText(/draft campaigns using this run/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeEnabled();
  });

  it("shows the blockers a refused delete returns and refreshes the preview", async () => {
    previewData = { ...root, blockers: [], warnings: [] };
    mutateAsync.mockRejectedValue(
      new ApiError("API error: 409", 409, {
        error: "delete_blocked_by_dependencies",
        blockers: [closedCampaign],
      }),
    );
    renderDialog();
    confirmWith("Run 2026-09-15");

    fireEvent.click(screen.getByRole("button", { name: "Force delete" }));

    expect(await screen.findByText(/kinase panel/i)).toBeInTheDocument();
    expect(refetch).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Force delete" })).toBeDisabled();
  });
});
