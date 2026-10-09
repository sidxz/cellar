import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { OntologySearchInput } from "./ontology-search-input";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
});

const MTB_USED = {
  term_id: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
  label: "Mycobacterium tuberculosis",
  ontology_source: "NCBITAXON",
  uri: null,
  short_label: "Mtb",
  protocol_count: 3,
};
const HUMAN_USED = {
  term_id: "http://purl.bioontology.org/ontology/NCBITAXON/9606",
  label: "Homo sapiens",
  ontology_source: "NCBITAXON",
  uri: null,
  short_label: "Human",
  protocol_count: 1,
};

const H37RV_USED = {
  term_id: "free_text:H37Rv",
  label: "H37Rv",
  ontology_source: "free_text",
  uri: null,
  short_label: "H37Rv",
  protocol_count: 2,
};

const MISSING_KEY =
  "Ontology search needs a BioPortal API key — an admin can add one under Admin → API Keys (key name 'bioportal').";

const search = vi.hoisted(() => vi.fn());
vi.mock("@/features/workspace-config/hooks/use-ontology-search", () => ({
  useOntologySearch: search,
  useTermsInUse: (slot?: string) => ({
    data:
      slot === "organism" ? [MTB_USED, HUMAN_USED] : slot === "strain" ? [H37RV_USED] : undefined,
  }),
  useOntologyDescendants: () => ({
    data: undefined,
    isLoading: false,
    error: new Error(`API error: 503 — ${MISSING_KEY}`),
  }),
}));

describe("OntologySearchInput", () => {
  beforeEach(() => search.mockReturnValue({ data: undefined, isLoading: false, error: null }));

  it("shows the server's reason without the HTTP status prefix", () => {
    render(
      <OntologySearchInput
        ontologySources={["BAO"]}
        rootConceptId="http://www.bioassayontology.org/bao#BAO_0000019"
        value={[]}
        onChange={() => {}}
        placeholder="Search BAO..."
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /search bao/i }));
    expect(screen.getByText(MISSING_KEY)).toBeInTheDocument();
    expect(screen.queryByText(/API error: 503/)).not.toBeInTheDocument();
  });

  it("lists the terms used here on focus, before anything is typed", () => {
    render(
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        slot="organism"
        value={[]}
        onChange={() => {}}
        placeholder="Search organism"
      />,
    );
    fireEvent.focus(screen.getByPlaceholderText("Search organism"));
    expect(screen.getByText("Used here")).toBeInTheDocument();
    expect(screen.getByText("Mycobacterium tuberculosis")).toBeInTheDocument();
    expect(screen.getByText("Homo sapiens")).toBeInTheDocument();
    expect(screen.getByText("3 protocols")).toBeInTheDocument();
  });

  it("filters the used terms as the chemist types, with no search results needed", () => {
    render(
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        slot="organism"
        value={[]}
        onChange={() => {}}
        placeholder="Search organism"
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Search organism"), {
      target: { value: "tuber" },
    });
    expect(screen.getByText("Mycobacterium tuberculosis")).toBeInTheDocument();
    expect(screen.queryByText("Homo sapiens")).not.toBeInTheDocument();
  });

  it("matches the short label and shows a used term once even when the search returns it", () => {
    search.mockReturnValue({
      data: [{ ...MTB_USED, short_label: undefined }],
      isLoading: false,
      error: null,
    });
    render(
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        slot="organism"
        value={[]}
        onChange={() => {}}
        placeholder="Search organism"
      />,
    );
    fireEvent.change(screen.getByPlaceholderText("Search organism"), { target: { value: "mtb" } });
    expect(screen.getAllByText("Mycobacterium tuberculosis")).toHaveLength(1);
  });

  it("shows no used-here group without a slot", () => {
    render(
      <OntologySearchInput
        ontologySources={["NCBITAXON"]}
        value={[]}
        onChange={() => {}}
        placeholder="Search organism"
      />,
    );
    fireEvent.focus(screen.getByPlaceholderText("Search organism"));
    expect(screen.queryByText("Used here")).not.toBeInTheDocument();
  });

  it("without ontologies offers the terms used here and free text, never an ontology search", () => {
    search.mockClear();
    const onChange = vi.fn();
    render(
      <OntologySearchInput
        ontologySources={[]}
        slot="strain"
        value={[]}
        onChange={onChange}
        allowFreeText
        placeholder="Type a strain"
      />,
    );
    fireEvent.focus(screen.getByPlaceholderText("Type a strain"));
    expect(screen.getByText("H37Rv")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Type a strain"), { target: { value: "3D7" } });
    for (const call of search.mock.calls) expect(call[2]).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /Free Text: "3D7"/ }));
    expect(onChange).toHaveBeenCalledWith([
      { term_id: "free_text:3D7", label: "3D7", ontology_source: "free_text", uri: null },
    ]);
  });
});
