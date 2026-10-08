import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
