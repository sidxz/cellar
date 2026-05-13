/**
 * Formula tokenization + validation for calculated readouts.
 *
 * The backend's asteval-based evaluator accepts standard Python identifier
 * syntax for variable names + a small math whitelist + numeric literals
 * + standard operators. Cross-protocol references (`@ProtocolName.ReadoutName`
 * or `@{Protocol Name}.Readout`) are a cellar extension that
 * `_CROSS_PROTOCOL_RE` catches before evaluation; the calc engine skips
 * those at compute time and the resolver handles them on read.
 *
 * Keep the math whitelist in sync with
 * `backend/src/cellar/infrastructure/computation/asteval_evaluator.py:_MATH_SYMBOLS`.
 */

/** Math symbols and constants the asteval evaluator exposes. */
export const FORMULA_MATH_SYMBOLS: readonly string[] = [
  "log",
  "log10",
  "log2",
  "sqrt",
  "abs",
  "pow",
  "min",
  "max",
  "round",
  "exp",
  "pi",
  "e",
] as const;

/** Cross-protocol reference: `@Protocol.Readout` or `@{Protocol Name}.Readout`.
 *  Mirrored from `backend/src/cellar/application/screening/readout_calculation_engine.py:_CROSS_PROTOCOL_RE`. */
const CROSS_PROTOCOL_RE = /@\{?[\w\s]+\}?\.[\w\s]+/g;

/** Bracket-wrapped reference: `[Name With Spaces]`. Lets formulas reference
 *  readouts whose names aren't valid Python identifiers. Mirrored from
 *  `backend/src/cellar/infrastructure/computation/asteval_evaluator.py:_BRACKET_REF_RE`. */
const BRACKET_REF_RE = /\[([^\[\]]+?)\]/g;

/** A standalone identifier outside of cross-protocol references. */
const IDENTIFIER_RE = /[A-Za-z_][A-Za-z0-9_]*/g;

export interface FormulaValidation {
  /** True if the formula is empty / not yet entered. */
  empty: boolean;
  /** Identifiers that aren't readouts, math symbols, or cross-protocol refs. */
  unknownIdentifiers: string[];
  /** Identifiers that DO match — useful for the "✓ N variables: a, b, c" hint. */
  knownReadouts: string[];
  /** True if the formula contains at least one cross-protocol ref. */
  hasCrossProtocolRefs: boolean;
}

/** Strip cross-protocol references from a formula so the remaining text can
 *  be tokenized for normal identifier checks. Returns the stripped formula
 *  and a boolean indicating whether any matches were stripped. */
function stripCrossProtocol(formula: string): { stripped: string; hadRefs: boolean } {
  const replaced = formula.replace(CROSS_PROTOCOL_RE, " ");
  return { stripped: replaced, hadRefs: replaced !== formula };
}

/** Strip bracket-wrapped references and collect the names inside. Returns
 *  the formula with each `[X]` replaced by a space, plus the list of names
 *  encountered (for downstream validation). */
function stripBrackets(formula: string): {
  stripped: string;
  bracketNames: string[];
} {
  const names: string[] = [];
  const stripped = formula.replace(BRACKET_REF_RE, (_m, name: string) => {
    const trimmed = name.trim();
    if (trimmed) names.push(trimmed);
    return " ";
  });
  return { stripped, bracketNames: names };
}

/** Validate a formula against the available readout names.
 *  Pure function; no I/O. Used for the live hint under the input.
 *
 *  Bracket references (`[Name With Spaces]`) and bare identifiers are
 *  both validated against `availableReadoutNames`. Cross-protocol refs
 *  are stripped before validation (resolved at read time on the BE).
 */
export function validateFormula(
  formula: string,
  availableReadoutNames: readonly string[],
): FormulaValidation {
  const trimmed = formula.trim();
  if (!trimmed) {
    return {
      empty: true,
      unknownIdentifiers: [],
      knownReadouts: [],
      hasCrossProtocolRefs: false,
    };
  }

  // Order matters: cross-protocol first (it can wrap names containing
  // brackets characters? — actually no, the BE regex uses [\w\s], no
  // brackets — but stripping cross-protocol first keeps the bracket
  // pass simpler). Then strip brackets so they don't confuse the
  // bare-identifier scan.
  const { stripped: noCross, hadRefs } = stripCrossProtocol(formula);
  const { stripped: bare, bracketNames } = stripBrackets(noCross);

  const readoutSet = new Set<string>(availableReadoutNames);
  const knownSet = new Set<string>([
    ...FORMULA_MATH_SYMBOLS,
    ...availableReadoutNames,
  ]);
  const unknown: string[] = [];
  const known: string[] = [];
  const seen = new Set<string>();

  // Bare identifiers (no brackets, no cross-protocol).
  for (const m of bare.matchAll(IDENTIFIER_RE)) {
    const ident = m[0];
    if (seen.has(ident)) continue;
    seen.add(ident);
    if (knownSet.has(ident)) {
      // Only flag readouts (not math symbols) as "known variables" in
      // the hint — math symbols are obvious.
      if (readoutSet.has(ident)) known.push(ident);
    } else {
      unknown.push(ident);
    }
  }

  // Bracket-wrapped names. Surface the user-facing form ([Name]) so the
  // hint matches what they typed.
  const bracketSeen = new Set<string>();
  for (const name of bracketNames) {
    if (bracketSeen.has(name)) continue;
    bracketSeen.add(name);
    if (readoutSet.has(name)) {
      if (!known.includes(name)) known.push(name);
    } else {
      unknown.push(`[${name}]`);
    }
  }

  return {
    empty: false,
    unknownIdentifiers: unknown,
    knownReadouts: known,
    hasCrossProtocolRefs: hadRefs,
  };
}

// ---------------------------------------------------------------------------
// Cursor-position helpers — used by the autocomplete popover to detect the
// "current token" the user is typing.
// ---------------------------------------------------------------------------

/** The token under or just before the cursor, as a `{kind, raw}` pair.
 *  Returns null when the cursor isn't on a completable token. */
export interface CurrentToken {
  /** "@protocol" — user just typed `@` or `@<partial>`; suggest protocols.
   *  "bracket"   — user is inside `[…]` typing a bracket-wrapped name;
   *                suggest readouts (any name, including space-containing).
   *  "ident"     — regular identifier; suggest readouts (single-word) + math.
   *  "none"      — cursor is on whitespace / operator; no completion. */
  kind: "ident" | "@protocol" | "bracket" | "none";
  /** The raw text under the cursor, e.g. `"Ra"`, `"@Pro"`, or `"[Raw A"`. */
  raw: string;
  /** Start position in the formula (so callers can replace [start, cursor)). */
  start: number;
}

/** Find the token the user is typing right now. */
export function tokenAtCursor(formula: string, cursorPos: number): CurrentToken {
  const before = formula.slice(0, cursorPos);
  // Bracket mode: trailing `[…` with no unmatched `]` between the `[` and
  // the cursor. Captures whatever the user has typed inside the bracket
  // so far so we can prefix-match readout names.
  const bracketMatch = before.match(/\[([^\]]*)$/);
  if (bracketMatch) {
    return {
      kind: "bracket",
      raw: bracketMatch[0],
      start: cursorPos - bracketMatch[0].length,
    };
  }
  // Match a trailing `@<word>?` (cross-protocol mode) or trailing `<word>`.
  const atMatch = before.match(/@[\w]*$/);
  if (atMatch) {
    return {
      kind: "@protocol",
      raw: atMatch[0],
      start: cursorPos - atMatch[0].length,
    };
  }
  const wordMatch = before.match(/[A-Za-z_][A-Za-z0-9_]*$/);
  if (wordMatch) {
    return {
      kind: "ident",
      raw: wordMatch[0],
      start: cursorPos - wordMatch[0].length,
    };
  }
  return { kind: "none", raw: "", start: cursorPos };
}

// ---------------------------------------------------------------------------
// Suggestions — given a current token, produce a ranked list of completions.
// ---------------------------------------------------------------------------

export type SuggestionKind = "readout" | "math" | "protocol";

export interface FormulaSuggestion {
  value: string;
  kind: SuggestionKind;
  /** Human-readable hint shown next to the value (e.g. "fn", "this protocol"). */
  hint?: string;
}

const MAX_SUGGESTIONS = 8;

/** Format a readout reference for insertion into a formula. Names with
 *  spaces (or other non-identifier chars) get bracket-wrapped so the BE
 *  preprocessor can resolve them. Single-word identifier-safe names are
 *  emitted bare. */
const IDENTIFIER_FULL_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
function formatReadoutRef(name: string): string {
  return IDENTIFIER_FULL_RE.test(name) ? name : `[${name}]`;
}

/** Generate suggestions for the given partial token.
 *  - `ident`     → match against readout names (prefix; identifier-safe
 *                  names emit bare, space-containing emit as `[Name]`)
 *                  + math whitelist
 *  - `bracket`   → user is inside `[…]`; match against ALL readout names
 *                  (substring), commit replaces the partial bracket with
 *                  the closed `[Name]` form
 *  - `@protocol` → match against protocol names; suggest with trailing `.`
 *  - `none`      → empty list
 */
export function buildSuggestions(
  token: CurrentToken,
  readoutNames: readonly string[],
  protocolNames: readonly string[],
): FormulaSuggestion[] {
  if (token.kind === "none") return [];

  if (token.kind === "@protocol") {
    const partial = token.raw.slice(1).toLowerCase();
    const matches = protocolNames.filter((n) =>
      n.toLowerCase().includes(partial),
    );
    return matches.slice(0, MAX_SUGGESTIONS).map((n) => ({
      // Names with spaces use `@{Name}.` syntax per the BE regex.
      value: n.includes(" ") ? `@{${n}}.` : `@${n}.`,
      kind: "protocol",
      hint: "protocol",
    }));
  }

  if (token.kind === "bracket") {
    // Inside `[…]`; the user can be matching ANY readout name (including
    // space-containing ones, which is the whole point of brackets).
    const partial = token.raw.slice(1).toLowerCase(); // drop leading `[`
    const hits: FormulaSuggestion[] = [];
    for (const n of readoutNames) {
      if (n.toLowerCase().includes(partial)) {
        hits.push({
          value: `[${n}]`,
          kind: "readout",
          hint: "readout",
        });
      }
    }
    hits.sort((a, b) => a.value.localeCompare(b.value));
    return hits.slice(0, MAX_SUGGESTIONS);
  }

  // ident mode
  const partial = token.raw.toLowerCase();
  if (!partial) return [];

  const readoutHits: FormulaSuggestion[] = [];
  for (const n of readoutNames) {
    // Prefix-match: standard for both bare and bracketed references.
    if (n.toLowerCase().startsWith(partial)) {
      readoutHits.push({
        value: formatReadoutRef(n),
        kind: "readout",
        hint: "readout",
      });
    }
  }
  // Sort prefix-matched readouts alphabetically; that's the most common case
  // and reads predictably.
  readoutHits.sort((a, b) => a.value.localeCompare(b.value));

  const mathHits: FormulaSuggestion[] = [];
  for (const fn of FORMULA_MATH_SYMBOLS) {
    if (fn.toLowerCase().startsWith(partial)) {
      mathHits.push({ value: fn, kind: "math", hint: "fn" });
    }
  }

  return [...readoutHits, ...mathHits].slice(0, MAX_SUGGESTIONS);
}
