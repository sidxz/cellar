import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtocolOptionLabel } from "./protocol-option-label";

describe("ProtocolOptionLabel", () => {
  it("shows just the name when there is no code", () => {
    const { container } = render(<ProtocolOptionLabel code={null} name="Legacy" />);
    expect(container.textContent).toBe("Legacy");
  });
});
