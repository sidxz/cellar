import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtocolOptionLabel } from "./protocol-option-label";

describe("ProtocolOptionLabel", () => {
  it("shows the code before the name", () => {
    render(<ProtocolOptionLabel code="PRT-00142" name="PptT inhibition [FP]" />);
    expect(screen.getByText("PRT-00142")).toBeInTheDocument();
    expect(screen.getByText("PptT inhibition [FP]")).toBeInTheDocument();
  });

  it("shows just the name when there is no code", () => {
    const { container } = render(<ProtocolOptionLabel code={null} name="Legacy" />);
    expect(container.textContent).toBe("Legacy");
  });
});
