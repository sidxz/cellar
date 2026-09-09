import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Molecule } from "../../types";
import { ProvenanceCard } from "./overview-tab";

function molecule(overrides: Partial<Molecule> = {}): Molecule {
  return {
    id: "m1",
    workspace_id: "ws",
    registration_number: "CC-000001",
    name: "Cpd",
    molecule_type: "small_molecule",
    structure: null,
    descriptors: null,
    molecular_formula: null,
    structure_status: "disclosed",
    registration_status: "approved",
    synthesis_status: "synthesized",
    lifecycle_stage: "registered",
    stereochemistry: null,
    invention_date: null,
    disclosed_at: null,
    merged_into_id: null,
    custom_fields: null,
    originating_org_id: "org",
    identifiers: [],
    version: 1,
    ...overrides,
  };
}

describe("ProvenanceCard", () => {
  it("shows the scientist and the declared disclosure date beside the recorded stamp", () => {
    render(
      <ProvenanceCard
        molecule={molecule({
          scientist_name: "A. Chemist",
          disclosure_date: "2024-03-15",
          disclosed_at: "2026-09-09T22:52:53Z",
        })}
      />,
    );
    expect(screen.getByText("Scientist")).toBeInTheDocument();
    expect(screen.getByText("A. Chemist")).toBeInTheDocument();
    expect(screen.getByText("Disclosure date")).toBeInTheDocument();
    expect(screen.getByText(/2024/)).toBeInTheDocument();
    expect(screen.getByText(/recorded .*2026/)).toBeInTheDocument();
  });

  it("renders nothing when there is no provenance to show", () => {
    const { container } = render(<ProvenanceCard molecule={molecule()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
