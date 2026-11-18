import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ColumnMappingBody } from "@/shared/lib/api/model";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import type { PreviewBulkRegistrationResponse } from "../../types/registration-wizard";

// The parse preview is usually already in the store, so that hook only fires in
// the test that clears it; the forecast hook is what the other tests drive.
const previewMock = vi.fn();
const forecastMock = vi.fn();
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  usePreviewBulkRegistration: () => ({
    mutateAsync: previewMock,
    isPending: false,
    isError: false,
    error: null,
  }),
  usePreviewRegistration: () => ({ mutateAsync: forecastMock, isPending: false }),
}));

import { StepPreview } from "./step-preview";

const parsed: PreviewBulkRegistrationResponse = {
  total_count: 5,
  error_count: 1,
  items: [
    {
      row_index: 0,
      file_row: 2,
      name: "SACC-1",
      smiles: "CCCCC",
      external_ids: [{ identifier: "JSF-1", identifier_type: "custom", source: "Synonyms" }],
      batch_ids: [{ identifier: "SACC-1-001", source: "CDD batch ID" }],
    },
    {
      row_index: 1,
      file_row: 3,
      name: "SACC-1",
      smiles: "CCCCC",
      external_ids: [],
      batch_ids: [{ identifier: "SACC-1-002", source: "CDD batch ID" }],
    },
    {
      row_index: 2,
      file_row: 4,
      name: null,
      smiles: null,
      external_ids: [],
      batch_ids: [],
      error: "Row 4: no name and no structure",
    },
    {
      row_index: 3,
      file_row: 5,
      name: "Old",
      smiles: "CCO",
      external_ids: [],
      batch_ids: [{ identifier: "OLD-001", source: "CDD batch ID" }],
    },
    { row_index: 4, file_row: 6, name: "Taken", smiles: "CCN", external_ids: [], batch_ids: [] },
  ],
};

const mapping: ColumnMappingBody = {
  columns: [
    { header: "Molecule Name", target: "name" },
    { header: "SMILES", target: "smiles" },
  ],
};

/** The number shown on the tile with this label, or null when the tile isn't shown. */
function tileValue(label: string): string | null {
  const badge = screen.queryAllByText(label).find((el) => el.getAttribute("data-slot") === "badge");
  const content = badge?.closest('[data-slot="card-content"]');
  return content?.querySelector(".tabular-nums")?.textContent ?? null;
}

beforeEach(() => {
  previewMock.mockReset();
  forecastMock.mockReset();
  // `index` is the position in the forecast request, which skips the parse-error row.
  forecastMock.mockResolvedValue({
    items: [
      { index: 0, action: "registered", compound_key: "KEY-1", batch_action: "new" },
      { index: 1, action: "registered", compound_key: "KEY-1", batch_action: "new" },
      {
        index: 2,
        action: "deduplicated",
        matched_molecule_id: "m-1",
        compound_key: "KEY-2",
        batch_action: "existing",
        matched_batch_number: "CC-000002-001",
      },
      {
        index: 3,
        action: "conflict",
        compound_key: "KEY-3",
        conflict_reason: "Identifier 'Taken' is already assigned to another molecule",
      },
    ],
  });
  useRegistrationWizard.getState().reset();
  const s = useRegistrationWizard.getState();
  useRegistrationWizard.setState({
    mode: "bulk",
    bulkInput: { ...s.bulkInput, file: new File(["x"], "rows.csv") },
    bulkMapping: mapping,
    bulkPreview: parsed,
  });
});

describe("StepPreview", () => {
  it("parses the file with the chosen column mapping", async () => {
    previewMock.mockResolvedValue(parsed);
    const file = useRegistrationWizard.getState().bulkInput.file;
    useRegistrationWizard.setState({ bulkPreview: null });
    render(<StepPreview />);
    await waitFor(() => expect(previewMock).toHaveBeenCalledTimes(1));
    expect(previewMock).toHaveBeenCalledWith({ file, mapping });
    await waitFor(() => expect(useRegistrationWizard.getState().bulkPreview).toBe(parsed));
  });

  it("asks the forecast only for parseable rows, with their batch IDs, and shows each row's compound and batch", async () => {
    // StrictMode double-invokes effects in dev; the forecast must still land.
    render(
      <StrictMode>
        <StepPreview />
      </StrictMode>,
    );

    // StrictMode issues the request twice in dev (first run cancelled); prod once.
    await waitFor(() => expect(forecastMock).toHaveBeenCalled());
    const sent = forecastMock.mock.calls.at(-1)?.[0].items;
    expect(sent).toHaveLength(4); // the parse-error row is not sent
    expect(sent[0]).toEqual({
      name: "SACC-1",
      smiles: "CCCCC",
      molecule_type: undefined,
      external_ids: [{ identifier: "JSF-1", identifier_type: "custom" }],
      batch_ids: ["SACC-1-001"],
    });

    expect(await screen.findByText("New")).toBeInTheDocument();
    expect(screen.getByText("Same as row 2")).toBeInTheDocument();
    expect(screen.getAllByText("New batch")).toHaveLength(2);
    expect(screen.getByText("Already in ChemCellar CC-000002-001")).toBeInTheDocument();
    // Problems are readable text in the Batch column, not hover-only.
    expect(screen.getByText("Row 4: no name and no structure")).toBeInTheDocument();
    expect(screen.getByText(/already assigned to another molecule/)).toBeInTheDocument();
    // Every ID it will store, with its Source.
    expect(screen.getByText("Synonyms · JSF-1")).toBeInTheDocument();
    expect(screen.getByText("CDD batch ID · SACC-1-001")).toBeInTheDocument();
  });

  it("says the forecast is unavailable when the request fails, never zeros", async () => {
    forecastMock.mockRejectedValue(new Error("boom"));
    render(<StepPreview />);
    expect(await screen.findByText(/forecast unavailable/i)).toBeInTheDocument();
    // Tiles that only the forecast can fill must not read as zeros.
    expect(tileValue("New compounds")).not.toBe("0");
    expect(tileValue("New batches")).not.toBe("0");
    expect(tileValue("Already in ChemCellar")).not.toBe("0");
    expect(screen.queryByText(/new compounds? ·/)).not.toBeInTheDocument();
  });

  it("counts rows, new compounds, new batches, batches already in ChemCellar and problems", async () => {
    render(<StepPreview />);
    expect(await screen.findByText("Same as row 2")).toBeInTheDocument();
    expect(tileValue("Rows")).toBe("5");
    expect(tileValue("New compounds")).toBe("1");
    expect(tileValue("New batches")).toBe("2");
    expect(tileValue("Already in ChemCellar")).toBe("1");
    expect(tileValue("Problems")).toBe("2");
    // The count sits next to the Register button, not inside it.
    expect(screen.getByText("1 new compound · 2 new batches")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Register" })).toBeEnabled();
    expect(screen.getByText(/forecast only/i)).toBeInTheDocument();
  });
});
