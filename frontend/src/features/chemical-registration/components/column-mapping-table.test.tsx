import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { ColumnMappingTable } from "./column-mapping-table";

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

describe("ColumnMappingTable", () => {
  it("disables a single-valued target taken by another row with the same label", () => {
    render(
      <ColumnMappingTable
        rows={[
          { key: "name", label: "Name" },
          { key: "molecule_fields.Name", label: "Name" },
        ]}
        mapping={{
          columns: [
            { header: "name", target: "name" },
            { header: "molecule_fields.Name", target: "ignore" },
          ],
        }}
        onChange={() => {}}
      />,
    );
    const [, second] = screen.getAllByRole("combobox", { name: "Where Name goes" });
    fireEvent.keyDown(second, { key: "Enter" });
    expect(screen.getByRole("option", { name: "Compound name (used by Name)" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });
});
