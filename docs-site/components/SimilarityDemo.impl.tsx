"use client";

import { useEffect, useState } from "react";
import { RdkitProvider, useRdkit } from "./RdkitProvider";
import { StructureViewerImpl } from "./StructureViewer.impl";

/** Fingerprint type used for the similarity calculation. */
export type FingerprintType = "morgan" | "rdkit" | "pattern";

export interface SimilarityDemoProps {
  /** Initial SMILES for the left/reference structure. */
  smilesA?: string;
  /** Initial SMILES for the right/query structure. */
  smilesB?: string;
  /** Fingerprint algorithm. Defaults to "morgan". */
  fingerprint?: FingerprintType;
  /** Morgan radius (when fingerprint = "morgan"). Defaults to 2. */
  radius?: number;
  /** Allow the reader to edit both SMILES. Defaults to true. */
  editable?: boolean;
  /** Extra CSS class for the outer container. */
  className?: string;
}

/** Bit length for the generated fingerprints. */
const FP_LENGTH = 2048;

/**
 * Computes a fingerprint bitstring for a molecule using the requested
 * algorithm via RDKit MinimalLib.
 *
 * MinimalLib exposes `get_morgan_fp` (circular / ECFP-like) and
 * `get_pattern_fp` (topological) — both return a string of "0"/"1" chars.
 * It has no dedicated RDKit-daylight `get_rdkit_fp`; the closest topological
 * fingerprint MinimalLib ships is the pattern fingerprint, so "rdkit" maps to
 * it (the docs surface a note explaining this).
 */
function fingerprintBits(
  mol: RdkitMol,
  fingerprint: FingerprintType,
  radius: number,
): string {
  if (fingerprint === "morgan") {
    return mol.get_morgan_fp(JSON.stringify({ radius, nBits: FP_LENGTH, len: FP_LENGTH }));
  }
  // "pattern" and "rdkit" both use the topological pattern fingerprint
  // (MinimalLib has no separate daylight/RDKit fingerprint).
  return mol.get_pattern_fp(JSON.stringify({ nBits: FP_LENGTH, len: FP_LENGTH }));
}

/**
 * Tanimoto (Jaccard) coefficient between two equal-length fingerprint
 * bitstrings: |A ∩ B| / |A ∪ B|. Two empty fingerprints are defined as
 * identical (1.0) to avoid a 0/0 NaN.
 */
function tanimoto(a: string, b: string): number {
  const len = Math.min(a.length, b.length);
  let inter = 0;
  let union = 0;
  for (let i = 0; i < len; i++) {
    const bitA = a.charCodeAt(i) === 49; // "1"
    const bitB = b.charCodeAt(i) === 49;
    if (bitA && bitB) inter++;
    if (bitA || bitB) union++;
  }
  return union === 0 ? 1 : inter / union;
}

// Minimal structural typing for the RDKit mol/module surface this widget uses,
// so we don't depend on the full @rdkit/rdkit types here.
interface RdkitMol {
  is_valid(): boolean;
  delete(): void;
  get_morgan_fp(options: string): string;
  get_pattern_fp(options: string): string;
}
interface RDKitMol {
  get_mol(smiles: string): RdkitMol | null;
}

type SimResult =
  | { kind: "idle" }
  | { kind: "computing" }
  | { kind: "ready"; score: number }
  | { kind: "invalid"; which: "A" | "B" | "both" }
  | { kind: "error" };

/**
 * Computes the Tanimoto similarity between two SMILES using the shared RDKit.js
 * WASM module (from RdkitProvider context). Recomputes whenever either SMILES,
 * the fingerprint type, or the radius changes. Emits structured states for a
 * graceful loading / invalid / error UX.
 */
function useSimilarity(
  smilesA: string,
  smilesB: string,
  fingerprint: FingerprintType,
  radius: number,
): SimResult {
  const { rdkit, status } = useRdkit();
  const [result, setResult] = useState<SimResult>({ kind: "idle" });

  useEffect(() => {
    if (status === "error") {
      setResult({ kind: "error" });
      return;
    }
    if (status !== "ready" || !rdkit) {
      setResult({ kind: "computing" });
      return;
    }
    if (!smilesA.trim() || !smilesB.trim()) {
      setResult({ kind: "idle" });
      return;
    }

    let cancelled = false;
    setResult({ kind: "computing" });

    const mod = rdkit as unknown as RDKitMol;
    let molA: RdkitMol | null = null;
    let molB: RdkitMol | null = null;

    try {
      molA = mod.get_mol(smilesA);
      molB = mod.get_mol(smilesB);
      const validA = !!molA && molA.is_valid();
      const validB = !!molB && molB.is_valid();

      if (!validA || !validB) {
        const which: "A" | "B" | "both" =
          !validA && !validB ? "both" : !validA ? "A" : "B";
        if (!cancelled) setResult({ kind: "invalid", which });
        return;
      }

      const bitsA = fingerprintBits(molA as RdkitMol, fingerprint, radius);
      const bitsB = fingerprintBits(molB as RdkitMol, fingerprint, radius);
      const score = tanimoto(bitsA, bitsB);

      if (!cancelled) setResult({ kind: "ready", score });
    } catch {
      if (!cancelled) setResult({ kind: "error" });
    } finally {
      molA?.delete();
      molB?.delete();
    }

    return () => {
      cancelled = true;
    };
  }, [rdkit, status, smilesA, smilesB, fingerprint, radius]);

  return result;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "0.4rem 0.55rem",
  borderRadius: "0.375rem",
  border: "1px solid color-mix(in srgb, currentColor 25%, transparent)",
  background: "transparent",
  color: "inherit",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  fontSize: "0.8125rem",
};

const labelTextStyle: React.CSSProperties = {
  display: "block",
  marginBottom: "0.25rem",
  fontWeight: 600,
  opacity: 0.8,
};

function fingerprintLabel(fingerprint: FingerprintType, radius: number): string {
  if (fingerprint === "morgan") return `Morgan (r=${radius})`;
  if (fingerprint === "pattern") return "Pattern (topological)";
  return "RDKit / topological";
}

/** Maps a similarity score [0,1] to a hue from red (0) through to green (1). */
function scoreColor(score: number): string {
  const hue = Math.round(score * 120); // 0 = red, 120 = green
  return `hsl(${hue}, 70%, 45%)`;
}

function ScoreReadout({
  result,
  fingerprint,
  radius,
}: {
  result: SimResult;
  fingerprint: FingerprintType;
  radius: number;
}) {
  let message: string | null = null;
  if (result.kind === "idle") message = "Enter two SMILES to compare";
  else if (result.kind === "computing") message = "Computing…";
  else if (result.kind === "error") message = "RDKit failed to load";
  else if (result.kind === "invalid") {
    message =
      result.which === "both"
        ? "Both SMILES are invalid"
        : `Structure ${result.which} is an invalid SMILES`;
  }

  const containerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "0.25rem",
    minHeight: 96,
    padding: "0.75rem 1rem",
    borderRadius: "0.5rem",
    border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
    background: "color-mix(in srgb, currentColor 4%, transparent)",
    textAlign: "center",
  };

  if (message) {
    return (
      <div role="status" style={{ ...containerStyle, color: "color-mix(in srgb, currentColor 60%, transparent)", fontSize: "0.8125rem" }}>
        {message}
      </div>
    );
  }

  const score = result.kind === "ready" ? result.score : 0;
  return (
    <div role="status" style={containerStyle}>
      <span style={{ fontSize: "0.75rem", fontWeight: 600, opacity: 0.7, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        Tanimoto similarity
      </span>
      <span
        style={{
          fontSize: "2rem",
          fontWeight: 700,
          lineHeight: 1.1,
          fontVariantNumeric: "tabular-nums",
          color: scoreColor(score),
        }}
      >
        {score.toFixed(3)}
      </span>
      <span style={{ fontSize: "0.75rem", opacity: 0.65 }}>
        {fingerprintLabel(fingerprint, radius)} · {FP_LENGTH} bits
      </span>
    </div>
  );
}

function SmilesField({
  label,
  value,
  onChange,
  editable,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  editable: boolean;
  placeholder: string;
}) {
  return (
    <label style={{ display: "block", fontSize: "0.8125rem" }}>
      <span style={labelTextStyle}>{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        readOnly={!editable}
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        style={{ ...inputStyle, opacity: editable ? 1 : 0.7 }}
      />
    </label>
  );
}

function SimilarityBody({
  smilesA,
  smilesB,
  fingerprint,
  radius,
}: {
  smilesA: string;
  smilesB: string;
  fingerprint: FingerprintType;
  radius: number;
}) {
  const result = useSimilarity(smilesA, smilesB, fingerprint, radius);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr",
          gap: "1rem",
          alignItems: "center",
          justifyItems: "center",
        }}
      >
        <div style={{ justifySelf: "center" }}>
          {smilesA.trim() ? (
            <StructureViewerImpl
              smiles={smilesA}
              width={220}
              height={170}
              editable={false}
            />
          ) : (
            <StructurePlaceholder />
          )}
        </div>

        <div style={{ minWidth: 160 }}>
          <ScoreReadout result={result} fingerprint={fingerprint} radius={radius} />
        </div>

        <div style={{ justifySelf: "center" }}>
          {smilesB.trim() ? (
            <StructureViewerImpl
              smiles={smilesB}
              width={220}
              height={170}
              editable={false}
            />
          ) : (
            <StructurePlaceholder />
          )}
        </div>
      </div>
    </div>
  );
}

function StructurePlaceholder() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 220,
        height: 170,
        borderRadius: "0.5rem",
        border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
        background: "color-mix(in srgb, currentColor 4%, transparent)",
        fontSize: "0.8125rem",
        color: "color-mix(in srgb, currentColor 60%, transparent)",
      }}
    >
      Enter a SMILES
    </div>
  );
}

/**
 * SimilarityDemo — Tanimoto similarity between two structures via RDKit.js
 * fingerprints (Morgan by default), with both structures rendered.
 *
 * Client-only; wraps its body in `RdkitProvider` so the WASM module loads once
 * per page and is shared with sibling chemistry widgets (and the two embedded
 * StructureViewers — no second WASM copy is loaded). The score recomputes live
 * as the reader edits either SMILES.
 */
export function SimilarityDemoImpl({
  smilesA,
  smilesB,
  fingerprint = "morgan",
  radius = 2,
  editable = true,
  className,
}: SimilarityDemoProps) {
  const [valueA, setValueA] = useState(smilesA ?? "");
  const [valueB, setValueB] = useState(smilesB ?? "");

  // Keep in sync if the props change (MDX hot reload / a different example).
  useEffect(() => {
    setValueA(smilesA ?? "");
  }, [smilesA]);
  useEffect(() => {
    setValueB(smilesB ?? "");
  }, [smilesB]);

  return (
    <RdkitProvider>
      <div
        className={className}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          margin: "1rem 0",
        }}
      >
        {/* Contract: `editable` lets the reader edit BOTH SMILES. When false the
            fields are shown read-only so the comparison stays inspectable. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "0.75rem",
          }}
        >
          <SmilesField
            label="Structure A (reference)"
            value={valueA}
            onChange={setValueA}
            editable={editable}
            placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
          />
          <SmilesField
            label="Structure B (query)"
            value={valueB}
            onChange={setValueB}
            editable={editable}
            placeholder="e.g. CC(=O)Nc1ccc(O)cc1"
          />
        </div>

        <SimilarityBody
          smilesA={valueA}
          smilesB={valueB}
          fingerprint={fingerprint}
          radius={radius}
        />
      </div>
    </RdkitProvider>
  );
}
