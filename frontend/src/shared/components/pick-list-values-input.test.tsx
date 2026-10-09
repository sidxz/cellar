import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { PickListValuesInput, addPickListValue } from "./pick-list-values-input";

describe("addPickListValue", () => {
  it("trims, ignores blanks and ignores duplicates case-insensitively", () => {
    expect(addPickListValue(["with"], "  without ")).toEqual(["with", "without"]);
    expect(addPickListValue(["With"], "with")).toEqual(["With"]);
    expect(addPickListValue(["with"], "   ")).toEqual(["with"]);
  });
});

function Harness({ initial = [] as string[] }) {
  const [v, setV] = useState(initial);
  return <PickListValuesInput values={v} onChange={setV} />;
}

describe("PickListValuesInput", () => {
  it("adds a chip on Enter and removes it with its x", () => {
    render(<Harness />);
    expect(screen.getByText("Add at least one value.")).toBeInTheDocument();
    const input = screen.getByPlaceholderText("Type a value, press Enter");
    fireEvent.change(input, { target: { value: "with" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByText("with")).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(screen.queryByText("Add at least one value.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove with" }));
    expect(screen.queryByText("with")).not.toBeInTheDocument();
  });
});
