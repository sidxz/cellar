import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { COLLECTION_TYPE_ICONS, CollectionTypeIcon } from "./collection-type-icon";

describe("CollectionTypeIcon", () => {
  it("maps every collection type to an icon", () => {
    const types = [
      "generic",
      "reference_set",
      "library",
      "hit_list",
      "series",
      "distribution_set",
    ] as const;
    for (const t of types) expect(COLLECTION_TYPE_ICONS[t]).toBeTruthy();
  });

  it("renders an svg", () => {
    const { container } = render(<CollectionTypeIcon type="library" />);
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
