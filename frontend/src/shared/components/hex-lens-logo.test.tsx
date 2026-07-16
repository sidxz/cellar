import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HexLensLogo } from "./hex-lens-logo";

describe("HexLensLogo", () => {
  it("renders the handle with currentColor so it adapts to theme", () => {
    const { container } = render(<HexLensLogo />);
    expect(container.querySelector("line")?.getAttribute("stroke")).toBe("currentColor");
  });

  it("gives each instance a unique gradient id (no collisions when rendered twice)", () => {
    const { container } = render(
      <>
        <HexLensLogo />
        <HexLensLogo />
      </>,
    );
    const ids = Array.from(container.querySelectorAll("linearGradient")).map((g) => g.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });
});
