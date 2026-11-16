import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { crossProtocol } from "../lib/cross-protocol-fixture";
import type { Dataset, DatasetColumn } from "../types";
import { FieldSelect } from "./field-select";

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const field = (key: string, label: string, group: string): DatasetColumn => ({
  key,
  label,
  kind: "category",
  group,
  provenance: {},
});

/** Fields whose labels match "seri" in every way: in order only, inside a word, at a
 * word's start, and at the start (the closer first). */
const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 0,
  row_ids: [],
  columns: [
    field("a", "Signal error index", "Readouts"),
    field("b", "Misericord", "Readouts"),
    field("c", "Plate series", "Details"),
    field("d", "Series of hits", "Details"),
    field("e", "Series", "Series"),
  ],
  values: {},
};

const options = () => screen.getAllByRole("option").map((o) => o.textContent);

describe("FieldSelect", () => {
  it("lists the closest start-of-label match first, then word, inside-word and in-order-letter matches", () => {
    render(<FieldSelect ds={ds} kinds={["category"]} value={undefined} onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.change(screen.getByPlaceholderText("Search fields…"), { target: { value: "Seri" } });
    expect(options()).toEqual([
      "Series",
      "Series of hitsDetails",
      "Plate seriesDetails",
      "MisericordReadouts",
      "Signal error indexReadouts",
    ]);
    fireEvent.click(screen.getByRole("option", { name: "Series" }));
  });

  it("shows a compared field by its own name, the protocol under it, the full label on hover", () => {
    render(<FieldSelect ds={crossProtocol} kinds={["number"]} value="dr:y:p" onChange={vi.fn()} />);
    const trigger = screen.getByRole("combobox");
    expect(trigger).toHaveAttribute("title", "Counter · pIC50");
    expect(within(trigger).getByText("pIC50")).toBeInTheDocument();
    expect(within(trigger).getByText("Counter")).toBeInTheDocument();
  });

  it("clears an optional field with None and picks by click", () => {
    const onChange = vi.fn();
    render(
      <FieldSelect
        ds={crossProtocol}
        kinds={["number"]}
        value="dr:y:p"
        onChange={onChange}
        clearable
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "None" }));
    expect(onChange).toHaveBeenLastCalledWith(undefined);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "Primary · pIC50" }));
    expect(onChange).toHaveBeenLastCalledWith("dr:x:p");
  });
});
