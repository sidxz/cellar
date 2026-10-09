import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { protocolCsvTemplate } from "../../lib/protocol-csv-import";
import { ProtocolCsvImportDialog } from "./protocol-csv-import-dialog";

const MTB = {
  term_id: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
  label: "Mycobacterium tuberculosis",
  ontology_source: "NCBITAXON",
  uri: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
};
const MIC_FORM = {
  id: "f-mic",
  workspace_id: "w",
  name: "MIC",
  category_id: "c-gi",
  is_default: true,
  protocol_type: "whole_cell",
  version: 1,
  readout_templates: [{ name: "MIC", data_type: "numeric", unit: "µM" }],
};

type Req = { url: string; method: string; params?: Record<string, unknown>; data?: unknown };
const state = vi.hoisted(() => ({
  existing: [] as string[],
  posts: [] as unknown[],
  failOn: null as string | null,
  saveText: vi.fn(),
  file: "",
}));
afterEach(() => {
  state.existing = [];
  state.posts = [];
  state.failOn = null;
  state.saveText.mockReset();
});

/** A preview name from the facts: organism, strain, then the category's words, then the discriminator. */
function previewFor(draft: {
  ontology_annotations?: Record<string, { label: string }[]>;
  discriminator?: string | null;
}) {
  const a = draft.ontology_annotations ?? {};
  const base = [a.organism?.[0]?.label, a.strain?.[0]?.label, "growth inhibition"]
    .filter(Boolean)
    .join(" ");
  const name = draft.discriminator ? `${base} (${draft.discriminator})` : base;
  return {
    name,
    base,
    missing: [],
    missing_labels: [],
    clash: state.existing.includes(name) ? { code: "PRT-0001", id: "p1", name } : null,
    siblings: [],
    needs_discriminator: false,
    discriminator_error: null,
    discriminator_in_pattern: false,
    sibling_renames: [],
  };
}

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: async ({ url, method, params, data }: Req) => {
    if (url === "/api/v1/protocol-categories")
      return [
        {
          id: "c-gi",
          workspace_id: "w",
          label: "Growth inhibition",
          name_pattern: "{organism} {strain?} growth inhibition",
          default_pattern: "",
          version: 1,
        },
      ];
    if (url === "/api/v1/protocol-forms") return [MIC_FORM];
    if (url === "/api/v1/targets") return { items: [], next_cursor: null };
    if (url === "/api/v1/ontology/terms-in-use") return [];
    if (url === "/api/v1/ontology/search") {
      expect(params?.exact_only).toBe(true);
      return params?.q === "Mtb" ? [MTB] : [];
    }
    if (url === "/api/v1/protocols/name-preview") return previewFor(data as never);
    if (url === "/api/v1/protocols" && method === "POST") {
      state.posts.push(data);
      const d = data as { discriminator: string | null; ontology_annotations: never };
      const name = previewFor(data as never).name;
      if (state.failOn && name.includes(state.failOn)) {
        throw new Error("API error: 409 — PRT-0009 already has this name");
      }
      state.existing.push(name);
      return { id: `id-${state.posts.length}`, code: `PRT-010${state.posts.length}`, name, d };
    }
    throw new Error(`unexpected ${method} ${url}`);
  },
}));
vi.mock("@/shared/lib/api/download", () => ({ saveText: state.saveText }));
vi.mock("@/shared/components/csv-dropzone", () => ({
  CsvDropzone: ({ onFile }: { onFile: (f: File) => void }) => (
    <button type="button" onClick={() => onFile(new File([state.file], "protocols.csv"))}>
      Upload
    </button>
  ),
}));
vi.mock("../../hooks/use-protocol-facet-slots", () => ({
  useProtocolFacetSlots: () =>
    [
      ["organism", "Organism", "NCBITAXON"],
      ["cell_line", "Cell line", "CLO"],
      ["strain", "Strain", ""],
    ].map(([name, label, source]) => ({
      id: `std:${name}`,
      name,
      label,
      ontology_sources: source ? [source] : [],
      root_concept_id: null,
      allow_free_text: true,
      is_required: false,
    })),
}));
vi.mock("@/shared/components/ontology-search-input", () => ({
  OntologySearchInput: ({
    onChange,
    placeholder,
  }: {
    onChange: (terms: unknown[]) => void;
    placeholder?: string;
  }) => (
    <input
      aria-label={placeholder}
      onChange={(e) => onChange([{ ...MTB, term_id: e.target.value, label: e.target.value }])}
    />
  ),
}));
vi.mock("../target-multi-select", () => ({ TargetMultiSelect: () => null }));

const HEADER = "category,organism,strain,discriminator,nicknames,references";

async function upload(csv: string) {
  state.file = csv;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ProtocolCsvImportDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));
  await screen.findByRole("table");
}

const rowOf = (line: number) => screen.getByTestId(`csv-row-${line}`);

describe("ProtocolCsvImportDialog", () => {
  it("downloads the template", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ProtocolCsvImportDialog open onOpenChange={() => {}} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /download template/i }));
    expect(state.saveText).toHaveBeenCalledWith(
      protocolCsvTemplate(),
      "protocol-import-template.csv",
    );
  });

  it("blocks an unresolved row until it is picked", async () => {
    await upload(`${HEADER}\nGrowth inhibition,Myco,,,,\nGrowth inhibition,Mtb,H37Rv,,,`);
    await within(rowOf(2)).findByText("Pick the organism");
    await within(rowOf(3)).findByText("Ready");
    expect(screen.getByRole("button", { name: "Create 1 protocol" })).toBeEnabled();

    fireEvent.change(within(rowOf(2)).getByLabelText(/search ncbitaxon/i), {
      target: { value: "Mycobacterium smegmatis" },
    });
    await within(rowOf(2)).findByText("Ready");
    expect(screen.getByRole("button", { name: "Create 2 protocols" })).toBeEnabled();
  });

  it("flags a clash with an existing protocol and within the file; a discriminator clears it", async () => {
    state.existing = ["Mycobacterium tuberculosis H37Rv growth inhibition"];
    await upload(
      `${HEADER}\nGrowth inhibition,Mtb,H37Rv,,,\nGrowth inhibition,Mtb,,,,\nGrowth inhibition,Mtb,,,,`,
    );
    await within(rowOf(2)).findByText("PRT-0001 already has this name: add a discriminator");
    await within(rowOf(3)).findByText("Same name as row 4 of this file: add a discriminator");
    await within(rowOf(4)).findByText("Same name as row 3 of this file: add a discriminator");
    expect(screen.getByRole("button", { name: "Create 0 protocols" })).toBeDisabled();

    const disc = within(rowOf(4)).getByLabelText("Discriminator");
    fireEvent.change(disc, { target: { value: "OD600" } });
    fireEvent.blur(disc);
    await within(rowOf(3)).findByText("Ready");
    await within(rowOf(4)).findByText("Ready");
  });

  it("creates two good rows in order and lists their codes", async () => {
    await upload(
      `${HEADER}\nGrowth inhibition,Mtb,H37Rv,,MABA,doi:10.1000/x\nGrowth inhibition,Mtb,Erdman,,,`,
    );
    await within(rowOf(3)).findByText("Ready");
    await within(rowOf(2)).findByText("Ready");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Create 2 protocols" }));
    });
    await screen.findByText(/PRT-0102/);
    expect(screen.getByText(/PRT-0101/)).toBeInTheDocument();
    expect(state.posts).toHaveLength(2);
    expect(state.posts[0]).toMatchObject({
      category: "Growth inhibition",
      form_id: "f-mic",
      nicknames: ["MABA"],
      references: [{ kind: "doi", value: "10.1000/x" }],
      ontology_annotations: { organism: [MTB] },
    });
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("keeps a failed row with its error", async () => {
    state.failOn = "Erdman";
    await upload(`${HEADER}\nGrowth inhibition,Mtb,H37Rv,,,\nGrowth inhibition,Mtb,Erdman,,,`);
    await within(rowOf(3)).findByText("Ready");
    await within(rowOf(2)).findByText("Ready");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Create 2 protocols" }));
    });
    await screen.findByText(/PRT-0101/);
    await waitFor(() => expect(screen.queryByTestId("csv-row-2")).not.toBeInTheDocument());
    expect(within(rowOf(3)).getByText("PRT-0009 already has this name")).toBeInTheDocument();
  });
});
