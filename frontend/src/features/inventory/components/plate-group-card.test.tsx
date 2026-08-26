import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { PlateGroupCard } from "./plate-group-card";

const node: PlateGroupNode = {
  id: "g1",
  name: "Vendor Library A",
  group_type: "vendor",
  description: "Legacy vendor set",
  parent_group_id: null,
  owner_org_id: "org1",
  plate_count: 3,
  created_by: "u1",
  version: 1,
  children: [],
  state: "Solubilized",
  storage_location_id: "loc-1",
  initial_volume_ul: 55,
  initial_concentration_mm: 10,
  compound_count: 17606,
  scientist: "Jane Doe",
  plate_format: "96",
  created_at: "2026-08-25T10:00:00Z",
};

describe("PlateGroupCard", () => {
  it("renders the pill, rows, and wires the action callbacks", () => {
    const onSelect = vi.fn();
    const onRequestLoan = vi.fn();
    render(
      <PlateGroupCard
        node={node}
        locationName="Room 1148 / Freezer 4"
        subtreePlates={3}
        selected={false}
        onSelect={onSelect}
        onRequestLoan={onRequestLoan}
      />,
    );

    expect(screen.getByText("Vendor Library A")).toBeInTheDocument();
    expect(screen.queryByText("vendor")).not.toBeInTheDocument();
    expect(screen.getByText("96-well · Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Room 1148 / Freezer 4")).toBeInTheDocument();
    expect(screen.getByText("Initial: 55 µL · 10 mM")).toBeInTheDocument();
    expect(screen.getByText("17,606 compounds")).toBeInTheDocument();
    expect(screen.getByText("3 plates")).toBeInTheDocument();
    expect(screen.queryByText(/created/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(onSelect).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Request loan" }));
    expect(onRequestLoan).toHaveBeenCalledTimes(1);
  });

  it("shows the group's own collection as a row", () => {
    render(
      <PlateGroupCard
        node={{ ...node, collection_id: "col-1", collection_name: "SACCZ" }}
        locationName={null}
        subtreePlates={3}
        selected={false}
        onSelect={vi.fn()}
        onRequestLoan={vi.fn()}
        inheritedCollection={{ id: "col-9", name: "Ignored" }}
      />,
    );
    expect(screen.getByText("Collection · SACCZ")).toBeInTheDocument();
    expect(screen.queryByText(/part of/)).not.toBeInTheDocument();
  });

  it("shows an inherited collection as a muted 'part of' row", () => {
    render(
      <PlateGroupCard
        node={node}
        locationName={null}
        subtreePlates={3}
        selected={false}
        onSelect={vi.fn()}
        onRequestLoan={vi.fn()}
        inheritedCollection={{ id: "col-1", name: "SACCZ" }}
      />,
    );
    expect(screen.getByText("part of SACCZ")).toBeInTheDocument();
    expect(screen.queryByText(/Collection ·/)).not.toBeInTheDocument();
  });

  it("hides Request loan when the subtree has no plates", () => {
    render(
      <PlateGroupCard
        node={{ ...node, plate_count: 0 }}
        locationName={null}
        subtreePlates={0}
        selected={false}
        onSelect={vi.fn()}
        onRequestLoan={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Request loan" })).not.toBeInTheDocument();
    expect(screen.queryByText(/plates/)).not.toBeInTheDocument();
  });
});
