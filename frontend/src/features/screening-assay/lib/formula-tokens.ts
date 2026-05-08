/**
 * Formula tokenization + validation for calculated readouts.
 *
 * The backend's asteval-based evaluator accepts standard Python identifier
 * syntax for variable names + a small math whitelist + numeric literals
 * + standard operators. Cross-protocol references (`@ProtocolName.ReadoutName`
 * or `@{Protocol Name}.Readout`) are a chem-vault extension that
 * `_CROSS_PROTOCOL_RE` catches before evaluation; the calc engine skips
 * those at compute time and the resolver handles them on read.
 *
 * Keep the math whitelist in sync with
 * `backend/src/chem_vault/infrastructure/computation/asteval_evaluator.py:_MATH_SYMBOLS`.
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
 *  Mirrored from `backend/src/chem_vault/application/screening/readout_calculation_engine.py:_CROSS_PROTOCOL_RE`. */
const CROSS_PROTOCOL_RE = /@\{?[\w\s]+\}?\.[\w\s]+/g;

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

/** Validate a formula against the available readout names.
 *  Pure function; no I/O. Used for the live hint under the input. */
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

  const { stripped, hadRefs } = stripCrossProtocol(formula);

  const knownSet = new Set<string>([
    ...FORMULA_MATH_SYMBOLS,
    ...availableReadoutNames,
  ]);
  const unknown: string[] = [];
  const known: string[] = [];
  const seen = new Set<string>();

  for (const m of stripped.matchAll(IDENTIFIER_RE)) {
    const ident = m[0];
    if (seen.has(ident)) continue;
    seen.add(ident);
    if (knownSet.has(ident)) {
      // Only flag readouts (not math symbols) as "known variables" in
      // the hint — math symbols are obvious.
      if (availableReadoutNames.includes(ident)) known.push(ident);
    } else {
      unknown.push(ident);
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
   *  "ident"     — regular identifier; suggest readouts + math.
   *  "none"      — cursor is on whitespace / operator; no completion. */
  kind: "ident" | "@protocol" | "none";
  /** The raw text under the cursor, e.g. `"Ra"` or `"@Pro"`. */
  raw: string;
  /** Start position in the formula (so callers can replace [start, cursor)). */
  start: number;
}

/** Find the token the user is typing right now. */
export function tokenAtCursor(formula: string, cursorPos: number): CurrentToken {
  const before = formula.slice(0, cursorPos);
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

/** Generate suggestions for the given partial token.
 *  - `ident` → match against readout names (prefix-priority) + math whitelist
 *  - `@protocol` → match against protocol names; suggest with trailing `.`
 *    so the user types fewer keystrokes
 *  - `none` → empty list
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

  // ident mode
  const partial = token.raw.toLowerCase();
  if (!partial) return [];

  const readoutHits: FormulaSuggestion[] = [];
  for (const n of readoutNames) {
    if (n.toLowerCase().startsWith(partial)) {
      readoutHits.push({ value: n, kind: "readout", hint: "readout" });
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
