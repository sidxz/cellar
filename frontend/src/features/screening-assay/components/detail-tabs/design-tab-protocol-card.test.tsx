import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { DesignTabProtocolCard } from "./design-tab-protocol-card";

// The design tab's direct/inherited partition MUST come from the rich
// GET /protocols/{id}/targets payload (is_direct / run_count) — the
// lightweight protocol.targets has no provenance. Regression guard for the
// bug where it filtered protocol.targets by an is_direct field that is never
// on that payload, classifying every target as inherited "from undefined
// runs" and making direct targets un-removable.

vi.mock("../../hooks/use-protocol-targets", () => ({
  useProtocolTargets: () => ({
    data: [
      {
        id: "t-direct",
        name: "Pks13",
        target_type: "single_protein",
        is_direct: true,
        run_count: 0,
      },
      {
        id: "t-inherited",
        name: "NadD",
        target_type: "single_protein",
        is_direct: false,
        run_count: 2,
      },
    ],
  }),
  invalidateProtocolTargetQueries: vi.fn(),
  useAddProtocolTarget: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoveProtocolTarget: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("../../hooks/use-protocols", () => ({
  useUpdateProtocol: () => ({ mutate: vi.fn(), isPending: false }),
  useSetOntologyAnnotation: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveOntologyAnnotation: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("../../hooks/use-targets", () => ({
  useTargets: () => ({
    data: [
      { id: "t-direct", name: "Pks13", target_type: "single_protein" },
      { id: "t-inherited", name: "NadD", target_type: "single_protein" },
    ],
  }),
}));

vi.mock("@/features/workspace-config/hooks/use-ontology-slots", () => ({
  useOntologySlots: () => ({ data: [] }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

function makeProtocol(overrides: Partial<Protocol> = {}): Protocol {
  return {
    id: "p-1",
    workspace_id: "ws-1",
    name: "Proto",
    description: null,
    protocol_type: "biochemical",
    // Lightweight effective list — deliberately WITHOUT provenance fields.
    targets: [
      { id: "t-direct", name: "Pks13", target_type: "single_protein" },
      { id: "t-inherited", name: "NadD", target_type: "single_protein" },
    ],
    category: null,
    protocol_version: 1,
    parent_protocol_id: null,
    status: "active",
    created_by: "u-1",
    dose_unit: "uM",
    pos_control_signal: "high",
    readout_definitions: [],
    condition_definitions: [],
    control_layouts: null,
    ontology_annotations: null,
    project_ids: [],
    recommended_hit_criteria: null,
    is_locked: false,
    locked_by: null,
    lock_reason: null,
    locked_at: null,
    ...overrides,
  } as Protocol;
}

describe("DesignTabProtocolCard targets partition", () => {
  it("classifies direct vs inherited from the rich targets payload", () => {
    render(<DesignTabProtocolCard protocol={makeProtocol()} protocolId="p-1" />);

    // The direct target seeds the multi-select (1 selected), not the
    // inherited section.
    expect(screen.getByText(/1 target selected/i)).toBeInTheDocument();

    // The inherited target renders with its real run count — never
    // "from undefined runs".
    expect(screen.getByText("NadD")).toBeInTheDocument();
    expect(screen.getByText(/from 2 runs/i)).toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it("renders direct targets as plain badges when editing is blocked", () => {
    render(<DesignTabProtocolCard protocol={makeProtocol({ is_locked: true })} protocolId="p-1" />);
    // Locked: no target multi-select; the direct target shows as a badge.
    // (queryByRole("combobox") would match the Control Convention select.)
    expect(screen.queryByText(/add a target/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/targets selected/i)).not.toBeInTheDocument();
    expect(screen.getByText("Pks13")).toBeInTheDocument();
  });
});
