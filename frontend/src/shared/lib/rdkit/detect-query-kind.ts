/**
 * Heuristic SMILES-vs-SMARTS classifier for substructure-search input.
 *
 * Runs purely client-side without RDKit so it can fire on every keystroke.
 * Drawing-derived input bypasses this — Ketcher tells us the format
 * directly. This is for the case where the chemist types into the input
 * box.
 *
 * Default: SMILES (matches commercial-tool behavior — typing 'c1ccccc1'
 * should search benzene, not be treated as a SMARTS pattern). Returns
 * SMARTS only when the string contains primitives that SMILES can't
 * express:
 *   - [! ...]  negation
 *   - [$( ...] recursive SMARTS
 *   - [N,O], [C;H1], [c&a]  atom lists / property AND inside brackets
 *   - *  any-atom (when not part of an atom-symbol)
 *   - ~  any-bond
 */
// `*` and `~` aren't part of standard SMILES syntax — any presence means
// the chemist is reaching for SMARTS semantics. `[!`, `[$(`, and `,;&`
// inside brackets are SMARTS-only primitives that no SMILES parser
// accepts.
const SMARTS_ONLY_SIGILS: RegExp[] = [
  /\[!/, // negation: [!#1]
  /\[\$\(/, // recursive: [$(...)]
  /\[[^\]]*[,;&][^\]]*\]/, // atom list / property AND inside brackets
  /\*/, // any-atom wildcard
  /~/, // any-bond
];

export function detectQueryKind(value: string): "smiles" | "smarts" {
  for (const re of SMARTS_ONLY_SIGILS) {
    if (re.test(value)) return "smarts";
  }
  return "smiles";
}
