import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import type { PreviewBulkRegistrationResponse } from "../../types/registration-wizard";

// The parse preview is already in the store, so that hook never fires; the
// forecast hook is what this test drives.
const forecastMock = vi.fn();
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  usePreviewBulkRegistration: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
  usePreviewRegistration: () => ({ mutateAsync: forecastMock, isPending: false }),
}));

import { StepPreview } from "./step-preview";

const parsed: PreviewBulkRegistrationResponse = {
  total_count: 4,
  error_count: 1,
  items: [
    { row_index: 0, name: "Fresh-1", smiles: "CCCCC", external_ids: [] },
    { row_index: 1, name: "Alias-2", smiles: "CCO", external_ids: [] },
    { row_index: 2, name: null, smiles: "not-parsed", external_ids: [], error: "bad row" },
    { row_index: 3, name: "Taken", smiles: "CCN", external_ids: [] },
  ],
};

beforeEach(() => {
  forecastMock.mockReset();
  forecastMock.mockResolvedValue({
    items: [
      { index: 0, action: "registered" },
      { index: 1, action: "deduplicated", matched_molecule_id: "m-1" },
      {
        index: 2,
        action: "conflict",
        conflict_reason: "Identifier 'Taken' is already assigned to another molecule",
      },
    ],
  });
  const s = useRegistrationWizard.getState();
  useRegistrationWizard.setState({
    bulkInput: { ...s.bulkInput, file: new File(["x"], "rows.csv") },
    bulkPreview: parsed,
  });
});

describe("StepPreview forecast", () => {
  it("asks the forecast only for parseable rows and shows one outcome per row", async () => {
    render(<StepPreview />);

    await waitFor(() => expect(forecastMock).toHaveBeenCalledTimes(1));
    const sent = forecastMock.mock.calls[0][0].items;
    expect(sent).toHaveLength(3); // the parse-error row is not sent
    expect(sent[0]).toMatchObject({ name: "Fresh-1", smiles: "CCCCC", external_ids: [] });

    expect(await screen.findByText("New")).toBeInTheDocument();
    expect(screen.getByText("Duplicate")).toBeInTheDocument();
    const conflict = screen.getByText("Conflict");
    expect(conflict).toBeInTheDocument();
    expect(conflict.closest("[title]")?.getAttribute("title")).toMatch(/already assigned/);
  });

  it("counts the forecast and says it is advisory", async () => {
    render(<StepPreview />);
    expect(await screen.findByText("Will register")).toBeInTheDocument();
    expect(screen.getByText("Duplicates")).toBeInTheDocument();
    expect(screen.getByText("Conflicts")).toBeInTheDocument();
    expect(screen.getByText(/forecast only/i)).toBeInTheDocument();
  });
});
