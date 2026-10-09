# Popovers meant to match their trigger's width shrink to their content

**Found:** 2026-10-08, protocol create-flow fix wave B, while fixing walk finding W2 ("µMConcentration" in unit
suggestions; docs/superpowers/reports/2026-10-08-chembl-naming-fit-test.md).

**Symptom.** Dropdowns that should be as wide as their input or button are as wide as their longest row instead. Rows
laid out with `justify-between` (unit + group) get no space between their two parts, and a narrow popover under a wide
trigger looks detached.

**Root cause.** Five components use the Tailwind v3 shorthand `w-[--radix-popover-trigger-width]`. Under Tailwind v4
that compiles to `width: --radix-popover-trigger-width;` (checked in the dev CSS bundle), which is invalid, so the
declaration is dropped. `cn()` (tailwind-merge) has already removed PopoverContent's default `w-72`, so the width ends
up `auto`. Affected: `shared/components/search-combobox.tsx`, `shared/components/searchable-select.tsx`,
`shared/components/ontology-search-input.tsx`, `screening-assay/components/target-multi-select.tsx`,
`screening-assay/components/collection-multi-select.tsx`. (`collection-section.tsx` uses
`w-[max(16rem,var(--radix-popover-trigger-width))]`, which is valid.)

**Fix direction.** Use the v4 form `w-(--radix-popover-trigger-width)`. This changes every caller's dropdown width at
once. Narrow triggers, such as the unit picker in a 160 px column, would then wrap their rows, so some callers want
`w-[max(16rem,var(--radix-popover-trigger-width))]` instead. Check each caller in the browser.

**Not done here.** This predates the create-flow branch and touches every shared picker. W2 was fixed locally with a
gap on the unit row (`unit-picker.tsx`).
