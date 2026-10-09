import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Tailwind v4 drops `w-[--var]` (v3 shorthand) as invalid CSS, so the popover
// ended up `width: auto`. Pickers must use the explicit var() form.
const PICKERS = [
  "src/shared/components/search-combobox.tsx",
  "src/shared/components/searchable-select.tsx",
  "src/shared/components/ontology-search-input.tsx",
  "src/features/screening-assay/components/target-multi-select.tsx",
  "src/features/screening-assay/components/collection-multi-select.tsx",
];

describe("picker popover width", () => {
  it.each(PICKERS)("%s uses the Tailwind v4 trigger-width class", (file) => {
    const src = readFileSync(file, "utf8");
    expect(src).not.toContain("w-[--radix-popover-trigger-width]");
    expect(src).toContain("w-[max(16rem,var(--radix-popover-trigger-width))]");
  });
});
