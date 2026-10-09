import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { ProtocolLibraryRow } from "./protocol-library-row";

const protocol = {
  id: "p",
  name: "PptT inhibition [FP]",
  code: "PRT-00042",
  protocol_type: "biochemical",
  status: "draft",
  targets: [],
  category: "Enzyme inhibition",
  readout_definitions: [],
} as unknown as Protocol;

describe("ProtocolLibraryRow", () => {
  it("shows the protocol code beside the name", () => {
    render(<ProtocolLibraryRow protocol={protocol} />);
    expect(screen.getByText("PRT-00042")).toBeInTheDocument();
    expect(screen.getByText("PptT inhibition [FP]")).toBeInTheDocument();
  });
});

describe("ProtocolLibraryRow search match", () => {
  it("says which field matched when it is not the name", () => {
    const withAlias = {
      ...protocol,
      aliases: [
        { label: "MABA", kind: "nickname", recorded_at: "2026-10-08T00:00:00Z", reason: null },
      ],
    } as unknown as Protocol;
    render(<ProtocolLibraryRow protocol={withAlias} search="maba" />);
    expect(screen.getByText("matched alias: MABA")).toBeInTheDocument();
  });

  it("says nothing extra when the name matched", () => {
    render(<ProtocolLibraryRow protocol={protocol} search="pptt" />);
    expect(screen.queryByText(/matched/)).not.toBeInTheDocument();
  });
});

describe("ProtocolLibraryRow menu", () => {
  it("offers New protocol from this, without selecting the row", () => {
    const onNewFrom = vi.fn();
    const onSelect = vi.fn();
    render(<ProtocolLibraryRow protocol={protocol} onSelect={onSelect} onNewFrom={onNewFrom} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Actions for PRT-00042" }), {
      key: "Enter",
    });
    fireEvent.click(screen.getByRole("menuitem", { name: "New protocol from this" }));
    expect(onNewFrom).toHaveBeenCalledWith(protocol);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("has no menu when the caller cannot create protocols", () => {
    render(<ProtocolLibraryRow protocol={protocol} />);
    expect(screen.queryByRole("button", { name: /Actions for/ })).not.toBeInTheDocument();
  });
});
