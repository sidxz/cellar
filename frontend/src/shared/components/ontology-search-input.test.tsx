import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { OntologySearchInput } from "./ontology-search-input";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
});

const MISSING_KEY =
  "Ontology search needs a BioPortal API key — an admin can add one under Admin → API Keys (key name 'bioportal').";

vi.mock("@/features/workspace-config/hooks/use-ontology-search", () => ({
  useOntologySearch: () => ({ data: undefined, isLoading: false, error: null }),
  useOntologyDescendants: () => ({
    data: undefined,
    isLoading: false,
    error: new Error(`API error: 503 — ${MISSING_KEY}`),
  }),
}));

describe("OntologySearchInput", () => {
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
});
