import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { BulkRegistrationMappingResponse, ColumnMappingBody } from "@/shared/lib/api/model";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { bulkStepIndex } from "../../types/registration-wizard";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither.
beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

// The real hooks run; only the HTTP edge is replaced.
const api = vi.hoisted(() => ({
  suggest: vi.fn<(headers: string[]) => Promise<ColumnMappingBody>>(),
  listSaved: vi.fn<() => Promise<BulkRegistrationMappingResponse[]>>(),
  save: vi.fn<(cfg: { url: string; method: string; data: unknown }) => Promise<unknown>>(),
}));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (cfg: { url: string; method: string; data: { headers: string[] } }) => {
    if (cfg.url === "/api/v1/bulk-registrations/suggest-mapping") {
      return api.suggest(cfg.data.headers);
    }
    if (cfg.url === "/api/v1/bulk-registration-mappings" && cfg.method === "GET") {
      return api.listSaved();
    }
    return api.save(cfg);
  },
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import { StepMapping } from "./step-mapping";

const HEADERS = [
  "Molecule Name",
  "SMILES",
  "Synonyms",
  "LGCY Batch Name",
  "Batch Name",
  "scientist",
];

/** What the server suggests for these headers by their names. */
const SUGGESTED: ColumnMappingBody = {
  columns: [
    { header: "Molecule Name", target: "name", source: null },
    { header: "SMILES", target: "smiles", source: null },
    { header: "Synonyms", target: "compound_id", source: "Synonyms" },
    { header: "LGCY Batch Name", target: "ignore", source: null },
    { header: "Batch Name", target: "ignore", source: null },
    { header: "scientist", target: "ignore", source: null },
  ],
};

const savedMapping = (
  id: string,
  name: string,
  columns: ColumnMappingBody["columns"],
): BulkRegistrationMappingResponse => ({
  id,
  name,
  columns,
  created_by: "u-1",
  created_at: null,
  updated_at: null,
});

/** Knows 5 of its 6 headers in this file (score 0.83), spelled differently. */
const CDD_EXPORT = savedMapping("m-cdd", "CDD export", [
  { header: "molecule_name", target: "name" },
  { header: "smiles", target: "smiles" },
  { header: "synonyms", target: "compound_id", source: "Synonyms" },
  { header: "LGCY Batch Name", target: "batch_id", source: "CDD legacy batch ID" },
  { header: "batch name", target: "ignore" },
  { header: "CDD Number", target: "ignore" },
]);

function renderStep() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <StepMapping />
    </QueryClientProvider>,
  );
}

const goesTo = (header: string) => screen.findByRole("combobox", { name: `Where ${header} goes` });

/** Opens a Radix select by keyboard and picks an option. */
async function choose(header: string, option: string) {
  fireEvent.keyDown(await goesTo(header), { key: "Enter" });
  fireEvent.click(screen.getByRole("option", { name: option }));
}

beforeEach(() => {
  api.suggest.mockReset().mockResolvedValue(SUGGESTED);
  api.listSaved.mockReset().mockResolvedValue([]);
  api.save.mockReset();
  useRegistrationWizard.getState().reset();
  const s = useRegistrationWizard.getState();
  useRegistrationWizard.setState({
    mode: "bulk",
    currentStep: bulkStepIndex("Match columns"),
    bulkInput: { ...s.bulkInput, file: new File(["x"], "export.csv"), fileFormat: "csv" },
    bulkColumns: {
      headers: HEADERS,
      samples: {
        "Molecule Name": ["SACC-0519397", "SACC-0519396"],
        SMILES: ["NC1=NC(N)=C2"],
        Synonyms: ["JSF-1187"],
        "LGCY Batch Name": ["MSD-065053252-001G001"],
        "Batch Name": ["001", "002"],
        scientist: [],
      },
    },
  });
});

describe("StepMapping", () => {
  it("asks the server where the file's headers go and shows its answer as 'Goes to'", async () => {
    renderStep();
    expect(await goesTo("Molecule Name")).toHaveTextContent("Compound name");
    expect(api.suggest).toHaveBeenCalledWith(HEADERS);
    expect(await goesTo("SMILES")).toHaveTextContent("Structure (SMILES)");
    expect(await goesTo("Synonyms")).toHaveTextContent("Compound ID");
    expect(await goesTo("Batch Name")).toHaveTextContent("Don't import");
    expect(screen.getByText("SACC-0519397, SACC-0519396")).toBeInTheDocument();
    expect(screen.getByText("(empty in this file)")).toBeInTheDocument();
    expect(useRegistrationWizard.getState().bulkMapping).toEqual(SUGGESTED);
  });

  it("offers 'Several values, separated by ;' for Compound ID and Batch ID only, and sets separator", async () => {
    renderStep();
    const box = await screen.findByRole("checkbox", {
      name: "Several values, separated by ; (Synonyms)",
    });
    expect(screen.getAllByRole("checkbox")).toHaveLength(1); // not for name, smiles, ignore
    fireEvent.click(box);
    await waitFor(() =>
      expect(
        useRegistrationWizard.getState().bulkMapping?.columns.find((c) => c.header === "Synonyms")
          ?.separator,
      ).toBe(";"),
    );
    fireEvent.click(box);
    await waitFor(() =>
      expect(
        useRegistrationWizard.getState().bulkMapping?.columns.find((c) => c.header === "Synonyms")
          ?.separator,
      ).toBeUndefined(),
    );
    await choose("LGCY Batch Name", "Batch ID");
    expect(
      screen.getByRole("checkbox", { name: "Several values, separated by ; (LGCY Batch Name)" }),
    ).toBeInTheDocument();
  });

  it("shows a Source, prefilled with the header, for a column sent to a labelled target", async () => {
    renderStep();
    expect(await screen.findByRole("textbox", { name: "Source for Synonyms" })).toHaveValue(
      "Synonyms",
    );
    expect(screen.queryByRole("textbox", { name: "Source for LGCY Batch Name" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Source for Molecule Name" })).toBeNull();

    await choose("LGCY Batch Name", "Batch ID");
    const source = screen.getByRole("textbox", { name: "Source for LGCY Batch Name" });
    expect(source).toHaveValue("LGCY Batch Name");

    fireEvent.change(source, { target: { value: "CDD legacy batch ID" } });
    expect(
      useRegistrationWizard
        .getState()
        .bulkMapping?.columns.find((c) => c.header === "LGCY Batch Name"),
    ).toEqual({ header: "LGCY Batch Name", target: "batch_id", source: "CDD legacy batch ID" });
  });

  it("disables a single-valued target in other rows once a column uses it", async () => {
    renderStep();
    fireEvent.keyDown(await goesTo("Batch Name"), { key: "Enter" });
    expect(
      screen.getByRole("option", { name: "Compound name (used by Molecule Name)" }),
    ).toHaveAttribute("aria-disabled", "true");
    // Compound ID takes any number of columns, so it stays open.
    const compoundId = screen.getByRole("option", { name: "Compound ID" });
    expect(compoundId).not.toHaveAttribute("aria-disabled");
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });

    // The column that uses it can still pick it.
    fireEvent.keyDown(await goesTo("Molecule Name"), { key: "Enter" });
    expect(screen.getByRole("option", { name: "Compound name" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it("blocks Preview with one sentence until a column goes to the name or the structure", async () => {
    api.suggest.mockResolvedValue({
      columns: HEADERS.map((header) => ({ header, target: "ignore" as const, source: null })),
    });
    renderStep();
    const sentence = "Pick the column with the compound name or the structure.";
    expect(await screen.findByText(sentence)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();

    await choose("Molecule Name", "Compound name");
    expect(screen.queryByText(sentence)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(useRegistrationWizard.getState().currentStep).toBe(bulkStepIndex("Preview"));
  });

  it("lays the best saved mapping scoring at least 0.7 over the suggestions and names it", async () => {
    const tooFew = savedMapping("m-low", "Half match", [
      { header: "Molecule Name", target: "compound_id", source: "Wrong" },
      { header: "Not in file", target: "name" },
    ]);
    api.listSaved.mockResolvedValue([tooFew, CDD_EXPORT]);
    renderStep();

    expect(await screen.findByRole("combobox", { name: "Saved mapping" })).toHaveTextContent(
      "CDD export",
    );
    expect(await goesTo("LGCY Batch Name")).toHaveTextContent("Batch ID");
    expect(screen.getByRole("textbox", { name: "Source for LGCY Batch Name" })).toHaveValue(
      "CDD legacy batch ID",
    );
    // The file's own spelling of every header stays.
    expect(
      useRegistrationWizard.getState().bulkMapping?.columns.map((c) => [c.header, c.target]),
    ).toEqual([
      ["Molecule Name", "name"],
      ["SMILES", "smiles"],
      ["Synonyms", "compound_id"],
      ["LGCY Batch Name", "batch_id"],
      ["Batch Name", "ignore"],
      ["scientist", "ignore"],
    ]);
  });

  it("keeps the suggestions when no saved mapping scores 0.7", async () => {
    api.listSaved.mockResolvedValue([
      savedMapping("m-low", "Half match", [
        { header: "Molecule Name", target: "compound_id", source: "Wrong" },
        { header: "Not in file", target: "name" },
      ]),
    ]);
    renderStep();
    expect(await screen.findByRole("combobox", { name: "Saved mapping" })).toHaveTextContent(
      "None",
    );
    await waitFor(() => expect(useRegistrationWizard.getState().bulkMapping).toEqual(SUGGESTED));
  });

  it("saves the mapping under a name, prefilled from the file name", async () => {
    api.save.mockResolvedValue(savedMapping("m-new", "export", SUGGESTED.columns));
    renderStep();
    await goesTo("Molecule Name");
    fireEvent.click(screen.getByRole("button", { name: "Save mapping…" }));
    expect(screen.getByLabelText("Name")).toHaveValue("export");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
    expect(api.save.mock.calls[0][0]).toMatchObject({
      url: "/api/v1/bulk-registration-mappings",
      method: "POST",
      data: { name: "export", columns: SUGGESTED.columns },
    });
  });

  it("offers to update the saved mapping it started from", async () => {
    api.listSaved.mockResolvedValue([CDD_EXPORT]);
    api.save.mockResolvedValue(CDD_EXPORT);
    renderStep();
    await screen.findByRole("combobox", { name: "Saved mapping" });
    await waitFor(() => expect(useRegistrationWizard.getState().bulkMapping).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Save mapping…" }));
    fireEvent.click(screen.getByRole("button", { name: "Update CDD export" }));
    await waitFor(() => expect(api.save).toHaveBeenCalledTimes(1));
    expect(api.save.mock.calls[0][0]).toMatchObject({
      url: "/api/v1/bulk-registration-mappings/m-cdd",
      method: "PATCH",
      data: {
        name: "CDD export",
        columns: useRegistrationWizard.getState().bulkMapping?.columns,
      },
    });
  });
});
