import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RunCompoundCell } from "./run-dr-results-cells";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

afterEach(cleanup);

const compound = {
  molecule_id: "rifampicin",
  registration_number: "CC-000985",
  molecule_name: "SACC-0078899",
  synonyms: ["CDD-3405855", "RIFAMPICIN"],
  batch_number: "CC-000985-001",
} as CompoundCurveRow;

describe("run compound identifiers", () => {
  it("surfaces a matching alias even when it normally sits behind the alias disclosure", () => {
    const { rerender } = render(<RunCompoundCell data={compound} />);
    expect(screen.getByText("RIFAMPICIN")).toBeInTheDocument();
    expect(screen.queryByText("CDD-3405855")).not.toBeInTheDocument();
    rerender(<RunCompoundCell data={compound} query="CDD-3405855" />);
    expect(screen.getByText("CDD-3405855")).toBeInTheDocument();
    expect(screen.getByText("CDD-3405855").tagName).toBe("MARK");
    expect(screen.getByRole("link", { name: "CC-000985" })).toHaveAttribute(
      "href",
      "/compounds/rifampicin",
    );
  });

  it("keeps all aliases and the batch accessible in the disclosure", () => {
    render(<RunCompoundCell data={compound} />);
    fireEvent.click(screen.getByRole("button", { name: "Show all aliases for CC-000985" }));
    expect(screen.getByText("CDD-3405855")).toBeVisible();
    expect(screen.getByRole("button", { name: "Copy all" })).toBeVisible();
    expect(screen.getAllByText(/CC-000985-001/).length).toBeGreaterThan(0);
  });
});
