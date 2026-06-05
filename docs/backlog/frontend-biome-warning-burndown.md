# Frontend biome warning burn-down

**Created:** 2026-06-05
**Context:** CI had been red since April; `pnpm lint` (biome) carried 1105 errors.
The 2026-06-05 CI-repair pass auto-fixed all format/organizeImports/safe-rule
errors and hand-fixed the small mechanical rules (noForEach, noParameterAssign,
noAccumulatingSpread, noGlobalIsNan, …). The judgment-heavy rules below were
deliberately downgraded from `error` to `warn` in `biome.json` so lint could
gate CI again without bundling ~270 behavior-relevant edits into a lint commit.

These are real findings, not noise — each needs a reviewed, per-case fix.
When a rule's count reaches zero, promote it back to `error` in `biome.json`.

## Outstanding warnings (as of 2026-06-05)

| Rule | Count | Risk if fixed mechanically |
|------|-------|---------------------------|
| `suspicious/noArrayIndexKey` | 77 | Wrong keys can break list reconciliation; many are static skeleton loops where index keys are acceptable — those should get scoped `biome-ignore` comments instead |
| `correctness/useExhaustiveDependencies` | 66 | **Highest risk.** Changing hook dep arrays can introduce refetch loops / stale closures (see the poll-storm incident). Fix per hook with UI verification |
| `suspicious/noExplicitAny` | 62 | Needs real types; many sit at API/grid boundaries |
| `style/noNonNullAssertion` | 57 | Replace `!` with guards/narrowing. NOTE: biome's auto-fix (`!` → `?.`) is NOT safe here — it changes crash-on-missing into silent undefined propagation and broke the type-check when attempted; fix by hand |
| `a11y/*` (noLabelWithoutControl 30, useSemanticElements 8, useKeyWithClickEvents 8, useButtonType 6, noSvgWithoutTitle 2) | 54 | Genuine accessibility gaps; fix alongside a UI pass |
| `correctness/noUnusedVariables` | 4 | Trivial; was already `warn` before this pass |

## Pre-existing strict-tsc finding (not a CI gate)

`pnpm exec tsc --noEmit` reports one error that predates this pass and is
invisible to `next build` (the CI gate, which passed on the same tree):

- `src/features/research-organization/components/results/molecule-card.test.tsx:40`
  — the test's `Molecule` literal sets `tags: []` but the (orval-aliased)
  `Molecule` type has no `tags` field. Either the test literal is stale or the
  type needs an orval regen against a backend exposing tags on the molecule DTO.

## Suggested order

1. `noUnusedVariables` + `noNonNullAssertion` (mechanical, low risk)
2. `noArrayIndexKey` (split: real keys vs justified `biome-ignore` for static lists)
3. `noExplicitAny` (type the API/grid boundaries)
4. a11y group (one feature area at a time)
5. `useExhaustiveDependencies` last, hook by hook, with manual UI verification
