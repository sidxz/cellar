"use client";

import { useEffect, useMemo, useState } from "react";
import { RdkitProvider, useRdkit } from "./RdkitProvider";

export interface SmilesAnnotatorProps {
  /** SMILES string to break down and annotate. Required. */
  smiles: string;
  /** Show the rendered 2D structure beside the annotated string. Default true. */
  showStructure?: boolean;
  /**
   * Optional explicit annotations keyed by token (or token index) — used to
   * override the built-in syntax descriptions for teaching purposes.
   */
  annotations?: Record<string, string>;
  /** Extra CSS class for the outer container. */
  className?: string;
}

/* ------------------------------------------------------------------ */
/* SMILES tokenizer + classifier                                       */
/* ------------------------------------------------------------------ */

type TokenKind =
  | "atom" // organic-subset atom, e.g. C N O c
  | "bracketAtom" // bracket atom incl. stereo/charge/H, e.g. [C@@H], [O-]
  | "bond" // - = # $ : / \
  | "ringClosure" // ring-bond digit or %nn
  | "branchOpen" // (
  | "branchClose" // )
  | "dot" // . disconnected components
  | "unknown";

interface Token {
  /** Raw text of the token as it appears in the SMILES. */
  text: string;
  /** Character offset where the token starts in the original string. */
  start: number;
  kind: TokenKind;
}

const ORGANIC_TWO_CHAR = new Set(["Cl", "Br"]);
const ORGANIC_ONE_CHAR = new Set([
  "B",
  "C",
  "N",
  "O",
  "P",
  "S",
  "F",
  "I",
  // aromatic organic subset
  "b",
  "c",
  "n",
  "o",
  "p",
  "s",
]);

const BOND_CHARS = new Set(["-", "=", "#", "$", ":", "/", "\\"]);

/**
 * Tokenize a SMILES string into syntactic tokens. This is a lightweight,
 * teaching-oriented lexer — it follows the OpenSMILES grammar closely enough
 * to label every character, and never throws on malformed input (unrecognized
 * characters become `unknown` tokens).
 */
function tokenizeSmiles(smiles: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  const n = smiles.length;

  while (i < n) {
    const ch = smiles[i];

    // Bracket atom: read until matching ']'
    if (ch === "[") {
      const close = smiles.indexOf("]", i);
      const end = close === -1 ? n : close + 1;
      tokens.push({ text: smiles.slice(i, end), start: i, kind: "bracketAtom" });
      i = end;
      continue;
    }

    // Branch
    if (ch === "(") {
      tokens.push({ text: ch, start: i, kind: "branchOpen" });
      i += 1;
      continue;
    }
    if (ch === ")") {
      tokens.push({ text: ch, start: i, kind: "branchClose" });
      i += 1;
      continue;
    }

    // Disconnected structures
    if (ch === ".") {
      tokens.push({ text: ch, start: i, kind: "dot" });
      i += 1;
      continue;
    }

    // Ring closure as %nn (two-digit ring bond number)
    if (ch === "%") {
      const text = smiles.slice(i, i + 3);
      tokens.push({ text, start: i, kind: "ringClosure" });
      i += text.length;
      continue;
    }

    // Ring closure as a single digit
    if (ch >= "0" && ch <= "9") {
      tokens.push({ text: ch, start: i, kind: "ringClosure" });
      i += 1;
      continue;
    }

    // Bonds
    if (BOND_CHARS.has(ch)) {
      tokens.push({ text: ch, start: i, kind: "bond" });
      i += 1;
      continue;
    }

    // Two-character organic atoms (Cl, Br) — check before single-char.
    const two = smiles.slice(i, i + 2);
    if (ORGANIC_TWO_CHAR.has(two)) {
      tokens.push({ text: two, start: i, kind: "atom" });
      i += 2;
      continue;
    }

    // Single-character organic-subset atoms
    if (ORGANIC_ONE_CHAR.has(ch)) {
      tokens.push({ text: ch, start: i, kind: "atom" });
      i += 1;
      continue;
    }

    // Anything else (incl. stray whitespace) — keep so nothing is dropped.
    tokens.push({ text: ch, start: i, kind: "unknown" });
    i += 1;
  }

  return tokens;
}

const AROMATIC_LOWER = new Set(["b", "c", "n", "o", "p", "s"]);

function elementName(symbol: string): string {
  const map: Record<string, string> = {
    B: "boron",
    C: "carbon",
    N: "nitrogen",
    O: "oxygen",
    P: "phosphorus",
    S: "sulfur",
    F: "fluorine",
    I: "iodine",
    Cl: "chlorine",
    Br: "bromine",
  };
  return map[symbol] ?? "";
}

const BOND_DESCRIPTIONS: Record<string, string> = {
  "-": "Single bond. Explicit single bonds are usually optional — adjacent atoms are single-bonded by default.",
  "=": "Double bond between the two adjacent atoms.",
  "#": "Triple bond between the two adjacent atoms.",
  $: "Quadruple bond (rare).",
  ":": "Aromatic bond — part of an aromatic ring system.",
  "/": "Directional bond used to specify cis/trans (E/Z) geometry around a double bond.",
  "\\": "Directional bond used to specify cis/trans (E/Z) geometry around a double bond.",
};

/** Human-readable explanation for a token, given its classification. */
function describeToken(token: Token, override?: string): {
  title: string;
  detail: string;
  category: string;
} {
  if (override) {
    return { title: token.text, detail: override, category: "Annotation" };
  }

  switch (token.kind) {
    case "atom": {
      const aromatic = AROMATIC_LOWER.has(token.text);
      const symbol = aromatic
        ? token.text.toUpperCase()
        : token.text;
      const name = elementName(symbol);
      const arom = aromatic
        ? " Lowercase means it is an aromatic atom (part of an aromatic ring)."
        : "";
      return {
        title: `Atom · ${symbol}`,
        detail: `${name ? `A ${name} atom.` : "An atom."} Written without brackets because it is in the “organic subset”, so hydrogens are filled in automatically to satisfy normal valence.${arom}`,
        category: "Atom",
      };
    }
    case "bracketAtom": {
      const inner = token.text.replace(/^\[|\]$/g, "");
      const features: string[] = [];
      if (/@@/.test(inner)) {
        features.push(
          "@@ marks tetrahedral stereochemistry (clockwise ordering of neighbors).",
        );
      } else if (/@/.test(inner)) {
        features.push(
          "@ marks tetrahedral stereochemistry (counter-clockwise ordering of neighbors).",
        );
      }
      if (/H\d*/.test(inner)) {
        features.push(
          "An explicit H count is given (e.g. H, H2) for hydrogens on this atom.",
        );
      }
      if (/[+-]/.test(inner)) {
        features.push("A formal charge is specified (+ or -).");
      }
      if (/^\d+/.test(inner)) {
        features.push("A leading number is the isotope mass.");
      }
      return {
        title: `Bracket atom · ${token.text}`,
        detail:
          `Square brackets let you spell out an atom exactly: isotope, charge, explicit hydrogens, and stereochemistry. ` +
          (features.length
            ? "Here: " + features.join(" ")
            : "Brackets are required whenever an atom falls outside the organic subset or needs explicit properties."),
        category: "Atom (bracket)",
      };
    }
    case "bond":
      return {
        title: `Bond · ${token.text}`,
        detail:
          BOND_DESCRIPTIONS[token.text] ?? "A bond between two atoms.",
        category:
          token.text === "/" || token.text === "\\" ? "Stereo bond" : "Bond",
      };
    case "ringClosure":
      return {
        title: `Ring closure · ${token.text}`,
        detail:
          token.text.startsWith("%")
            ? "A two-digit ring-bond label (%nn). The matching label elsewhere closes the ring by bonding the two atoms."
            : "A ring-bond number. The same digit appears twice; those two atoms are bonded to close the ring.",
        category: "Ring",
      };
    case "branchOpen":
      return {
        title: "Branch open · (",
        detail:
          "Opens a branch. Atoms inside the parentheses hang off the atom written just before the “(”.",
        category: "Branch",
      };
    case "branchClose":
      return {
        title: "Branch close · )",
        detail:
          "Closes a branch and returns to the atom the branch sprouted from, so the main chain can continue.",
        category: "Branch",
      };
    case "dot":
      return {
        title: "Disconnection · .",
        detail:
          "Separates disconnected components (e.g. a salt and its counter-ion), describing more than one molecule in one string.",
        category: "Disconnection",
      };
    default:
      return {
        title: `Unrecognized · ${token.text}`,
        detail:
          "This character is not part of the basic SMILES syntax this guide covers (or it is whitespace).",
        category: "Other",
      };
  }
}

const KIND_COLORS: Record<TokenKind, string> = {
  atom: "#2563eb", // blue
  bracketAtom: "#7c3aed", // violet
  bond: "#16a34a", // green
  ringClosure: "#ea580c", // orange
  branchOpen: "#0891b2", // cyan
  branchClose: "#0891b2",
  dot: "#dc2626", // red
  unknown: "#6b7280", // gray
};

/* ------------------------------------------------------------------ */
/* Structure render (shared RDKit module via context)                  */
/* ------------------------------------------------------------------ */

type RenderState =
  | { kind: "loading" }
  | { kind: "ready"; url: string }
  | { kind: "invalid" }
  | { kind: "error" };

function StructureCanvas({
  smiles,
  width,
  height,
}: {
  smiles: string;
  width: number;
  height: number;
}) {
  const { rdkit, status } = useRdkit();
  const [render, setRender] = useState<RenderState>({ kind: "loading" });

  useEffect(() => {
    if (status === "error") {
      setRender({ kind: "error" });
      return;
    }
    if (status !== "ready" || !rdkit) {
      setRender({ kind: "loading" });
      return;
    }
    if (!smiles.trim()) {
      setRender({ kind: "invalid" });
      return;
    }

    let cancelled = false;
    let url: string | null = null;

    try {
      const mol = rdkit.get_mol(smiles);
      if (!mol || !mol.is_valid()) {
        mol?.delete();
        setRender({ kind: "invalid" });
        return;
      }
      const svgStr = mol.get_svg(width, height);
      mol.delete();
      const blob = new Blob([svgStr], { type: "image/svg+xml" });
      url = URL.createObjectURL(blob);
      if (!cancelled) setRender({ kind: "ready", url });
    } catch {
      if (!cancelled) setRender({ kind: "error" });
    }

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [rdkit, status, smiles, width, height]);

  const frameStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width,
    height,
    borderRadius: "0.5rem",
    border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
    background: "color-mix(in srgb, currentColor 4%, transparent)",
    fontSize: "0.8125rem",
    color: "color-mix(in srgb, currentColor 60%, transparent)",
    overflow: "hidden",
    flex: "0 0 auto",
  };

  if (render.kind === "ready") {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={render.url}
        alt={`Chemical structure for SMILES ${smiles}`}
        width={width}
        height={height}
        className="dark:invert"
        style={{ borderRadius: "0.5rem", flex: "0 0 auto" }}
      />
    );
  }

  let message = "Loading RDKit…";
  if (render.kind === "invalid") message = "Invalid SMILES";
  else if (render.kind === "error") message = "RDKit failed to load";

  return (
    <div style={frameStyle} role="img" aria-label={message}>
      {message}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Annotated SMILES string                                             */
/* ------------------------------------------------------------------ */

function AnnotatedSmiles({
  tokens,
  annotations,
  activeIndex,
  onActivate,
}: {
  tokens: Token[];
  annotations?: Record<string, string>;
  activeIndex: number | null;
  onActivate: (index: number | null) => void;
}) {
  return (
    <div
      style={{
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: "1.25rem",
        lineHeight: 1.9,
        wordBreak: "break-all",
      }}
    >
      {tokens.map((token, idx) => {
        const isActive = idx === activeIndex;
        const color = KIND_COLORS[token.kind];
        const annotatable = token.kind !== "unknown";
        return (
          <button
            key={`${token.start}-${idx}`}
            type="button"
            onMouseEnter={() => onActivate(idx)}
            onFocus={() => onActivate(idx)}
            onClick={() => onActivate(isActive ? null : idx)}
            onBlur={() => onActivate(null)}
            aria-pressed={isActive}
            aria-label={`SMILES token ${token.text}`}
            style={{
              all: "unset",
              cursor: annotatable ? "pointer" : "default",
              padding: "0.05em 0.12em",
              margin: "0 0.01em",
              borderRadius: "0.25rem",
              color,
              fontWeight: 600,
              borderBottom: `2px solid ${
                isActive ? color : "transparent"
              }`,
              background: isActive
                ? "color-mix(in srgb, currentColor 10%, transparent)"
                : "transparent",
              transition: "background 0.1s ease, border-color 0.1s ease",
              whiteSpace: "pre",
            }}
          >
            {token.text}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main widget                                                         */
/* ------------------------------------------------------------------ */

/**
 * SmilesAnnotator — hover (or tap/focus) each token of a SMILES string to see
 * what it means: atoms, bonds, ring closures, branches, and stereo. Teaches
 * SMILES syntax, with a live RDKit.js 2D render of the molecule beside it.
 *
 * Client-only; wraps its structure canvas in `RdkitProvider` so the WASM
 * module loads once per page and is shared with sibling chemistry widgets.
 */
export function SmilesAnnotatorImpl({
  smiles,
  showStructure = true,
  annotations,
  className,
}: SmilesAnnotatorProps) {
  const tokens = useMemo(() => tokenizeSmiles(smiles), [smiles]);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Reset selection if the SMILES (and thus the token list) changes.
  useEffect(() => {
    setActiveIndex(null);
  }, [smiles]);

  const activeToken = activeIndex != null ? tokens[activeIndex] : null;
  const override = activeToken
    ? annotations?.[activeToken.text] ??
      (activeIndex != null ? annotations?.[String(activeIndex)] : undefined)
    : undefined;
  const description = activeToken
    ? describeToken(activeToken, override)
    : null;

  return (
    <RdkitProvider>
      <div
        className={className}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          margin: "1rem 0",
          padding: "1rem",
          border:
            "1px solid color-mix(in srgb, currentColor 15%, transparent)",
          borderRadius: "0.75rem",
        }}
      >
        <div
          style={{
            display: "flex",
            gap: "1.25rem",
            alignItems: "flex-start",
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: "1 1 280px", minWidth: 0 }}>
            <p
              style={{
                margin: "0 0 0.5rem",
                fontSize: "0.75rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                opacity: 0.6,
              }}
            >
              Hover or tap a token
            </p>
            <AnnotatedSmiles
              tokens={tokens}
              annotations={annotations}
              activeIndex={activeIndex}
              onActivate={setActiveIndex}
            />
          </div>

          {showStructure ? (
            <StructureCanvas smiles={smiles} width={220} height={180} />
          ) : null}
        </div>

        {/* Explanation panel — fixed-height so layout doesn't jump. */}
        <div
          aria-live="polite"
          style={{
            minHeight: 76,
            padding: "0.75rem 0.875rem",
            borderRadius: "0.5rem",
            background: "color-mix(in srgb, currentColor 5%, transparent)",
            border:
              "1px solid color-mix(in srgb, currentColor 10%, transparent)",
            fontSize: "0.875rem",
          }}
        >
          {description ? (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "0.5rem",
                  marginBottom: "0.25rem",
                }}
              >
                <span style={{ fontWeight: 700 }}>{description.title}</span>
                <span
                  style={{
                    fontSize: "0.6875rem",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                    opacity: 0.6,
                  }}
                >
                  {description.category}
                </span>
              </div>
              <p style={{ margin: 0, opacity: 0.9 }}>{description.detail}</p>
            </>
          ) : (
            <p style={{ margin: 0, opacity: 0.65 }}>
              Move your pointer over the colored tokens above (or tap on touch
              devices) to learn what each part of the SMILES string means.
            </p>
          )}
        </div>
      </div>
    </RdkitProvider>
  );
}
