"use client";

import { useEffect, useMemo, useState } from "react";
import { RdkitProvider, useRdkit } from "./RdkitProvider";
import { StructureViewerImpl } from "./StructureViewer.impl";

/** RDKit-computed descriptors surfaced by the calculator. */
export type PropertyKey =
  | "mw"
  | "logp"
  | "tpsa"
  | "hbd"
  | "hba"
  | "rotatableBonds"
  | "rings"
  | "formula";

export interface PropertyCalculatorProps {
  /** Initial SMILES. When omitted, the widget shows an input. */
  smiles?: string;
  /** Which descriptors to display. Defaults to MW/logP/TPSA/HBD/HBA. */
  properties?: PropertyKey[];
  /** Allow the reader to edit the SMILES. Defaults to true. */
  editable?: boolean;
  /** Show the 2D structure alongside the property table. Defaults to true. */
  showStructure?: boolean;
  /** Extra CSS class for the outer container. */
  className?: string;
}

const DEFAULT_PROPERTIES: PropertyKey[] = ["mw", "logp", "tpsa", "hbd", "hba"];

/** Display metadata for each descriptor: label, formatter, and units. */
const PROPERTY_META: Record<
  PropertyKey,
  { label: string; format: (v: number | string) => string }
> = {
  mw: { label: "MW", format: (v) => `${(v as number).toFixed(2)} g/mol` },
  logp: { label: "logP", format: (v) => (v as number).toFixed(2) },
  tpsa: { label: "TPSA", format: (v) => `${(v as number).toFixed(2)} Å²` },
  hbd: { label: "HBD", format: (v) => String(v) },
  hba: { label: "HBA", format: (v) => String(v) },
  rotatableBonds: { label: "Rotatable bonds", format: (v) => String(v) },
  rings: { label: "Rings", format: (v) => String(v) },
  formula: { label: "Formula", format: (v) => String(v) },
};

type Descriptors = Record<PropertyKey, number | string>;

type CalcState =
  | { kind: "idle" }
  | { kind: "computing" }
  | { kind: "ready"; values: Descriptors }
  | { kind: "invalid" }
  | { kind: "error" };

/**
 * Extracts the molecular formula from an RDKit-generated InChI string.
 * The formula is the first layer after the version prefix, e.g.
 * `InChI=1S/C9H8O4/c...` → `C9H8O4`.
 */
function formulaFromInchi(inchi: string): string {
  const parts = inchi.split("/");
  return parts.length > 1 ? parts[1] : "—";
}

/**
 * Computes RDKit descriptors for a SMILES string using the shared RDKit.js
 * WASM module (from RdkitProvider context). Re-runs whenever the SMILES
 * changes; emits structured render states for graceful loading/error UX.
 *
 * Descriptor sources (RDKit MinimalLib `get_descriptors()` JSON):
 *   mw → amw · logp → CrippenClogP · tpsa → tpsa · hbd → NumHBD ·
 *   hba → NumHBA · rotatableBonds → NumRotatableBonds · rings → NumRings.
 * Formula is parsed from `get_inchi()` (no formula key in get_descriptors).
 */
function usePropertyCalc(smiles: string): CalcState {
  const { rdkit, status } = useRdkit();
  const [state, setState] = useState<CalcState>({ kind: "idle" });

  useEffect(() => {
    if (status === "error") {
      setState({ kind: "error" });
      return;
    }
    if (status !== "ready" || !rdkit) {
      setState({ kind: "computing" });
      return;
    }
    if (!smiles.trim()) {
      setState({ kind: "idle" });
      return;
    }

    let cancelled = false;
    setState({ kind: "computing" });

    try {
      const mol = rdkit.get_mol(smiles);
      if (!mol || !mol.is_valid()) {
        mol?.delete();
        if (!cancelled) setState({ kind: "invalid" });
        return;
      }

      const d = JSON.parse(mol.get_descriptors()) as Record<string, number>;

      let formula = "—";
      try {
        formula = formulaFromInchi(mol.get_inchi());
      } catch {
        // InChI generation can fail for exotic structures; leave placeholder.
      }
      mol.delete();

      const values: Descriptors = {
        mw: d.amw,
        logp: d.CrippenClogP,
        tpsa: d.tpsa,
        hbd: d.NumHBD,
        hba: d.NumHBA,
        rotatableBonds: d.NumRotatableBonds,
        rings: d.NumRings,
        formula,
      };

      if (!cancelled) setState({ kind: "ready", values });
    } catch {
      if (!cancelled) setState({ kind: "error" });
    }

    return () => {
      cancelled = true;
    };
  }, [rdkit, status, smiles]);

  return state;
}

const cellStyle: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid color-mix(in srgb, currentColor 12%, transparent)",
  fontSize: "0.8125rem",
};

function PropertyTable({
  properties,
  state,
}: {
  properties: PropertyKey[];
  state: CalcState;
}) {
  let message: string | null = null;
  if (state.kind === "idle") message = "Enter a SMILES to compute properties";
  else if (state.kind === "computing") message = "Computing…";
  else if (state.kind === "invalid") message = "Invalid SMILES";
  else if (state.kind === "error") message = "RDKit failed to load";

  if (message) {
    return (
      <div
        role="status"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: 120,
          borderRadius: "0.5rem",
          border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
          background: "color-mix(in srgb, currentColor 4%, transparent)",
          fontSize: "0.8125rem",
          color: "color-mix(in srgb, currentColor 60%, transparent)",
        }}
      >
        {message}
      </div>
    );
  }

  const values = state.kind === "ready" ? state.values : null;

  return (
    <table
      style={{
        borderCollapse: "collapse",
        width: "100%",
        borderRadius: "0.5rem",
        overflow: "hidden",
        border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
      }}
    >
      <tbody>
        {properties.map((key) => {
          const meta = PROPERTY_META[key];
          const raw = values ? values[key] : undefined;
          const display =
            raw === undefined || raw === null || (typeof raw === "number" && Number.isNaN(raw))
              ? "—"
              : meta.format(raw);
          return (
            <tr key={key}>
              <th
                scope="row"
                style={{
                  ...cellStyle,
                  textAlign: "left",
                  fontWeight: 600,
                  width: "45%",
                  opacity: 0.85,
                }}
              >
                {meta.label}
              </th>
              <td
                style={{
                  ...cellStyle,
                  textAlign: "right",
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                }}
              >
                {display}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function PropertyCalculatorBody({
  smiles,
  properties,
  editable,
  showStructure,
}: {
  smiles: string;
  properties: PropertyKey[];
  editable: boolean;
  showStructure: boolean;
}) {
  const state = usePropertyCalc(smiles);

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "1rem",
        alignItems: "flex-start",
      }}
    >
      {showStructure && smiles.trim() ? (
        <div style={{ flex: "0 0 auto" }}>
          {/* Reuse the StructureViewer canvas; it consumes the same shared
              RdkitProvider, so no second WASM copy is loaded. Render only when
              there's a SMILES so it never falls back to its own input field —
              this widget owns the single SMILES input. */}
          <StructureViewerImpl
            smiles={smiles}
            width={240}
            height={180}
            editable={false}
          />
        </div>
      ) : null}
      <div style={{ flex: "1 1 220px", minWidth: 220 }}>
        <PropertyTable properties={properties} state={state} />
      </div>
    </div>
  );
}

/**
 * PropertyCalculator — SMILES in, live RDKit-computed descriptors out.
 *
 * Client-only; wraps its body in `RdkitProvider` so the WASM module loads once
 * per page and is shared with sibling chemistry widgets (and the embedded
 * StructureViewer). Descriptors recompute live as the reader edits the SMILES.
 */
export function PropertyCalculatorImpl({
  smiles,
  properties = DEFAULT_PROPERTIES,
  editable = true,
  showStructure = true,
  className,
}: PropertyCalculatorProps) {
  // Contract: "When omitted, the widget shows an input." Always show the input
  // when there's no initial SMILES, regardless of `editable`.
  const showInput = editable || !smiles;
  const [value, setValue] = useState(smiles ?? "");

  // Keep in sync if the prop changes (MDX hot reload / a different example).
  useEffect(() => {
    setValue(smiles ?? "");
  }, [smiles]);

  // Stabilize the property list so the table/effect deps don't churn.
  const propertyList = useMemo(() => properties, [properties]);

  return (
    <RdkitProvider>
      <div
        className={className}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
          margin: "1rem 0",
        }}
      >
        {showInput ? (
          <label style={{ display: "block", fontSize: "0.8125rem" }}>
            <span
              style={{
                display: "block",
                marginBottom: "0.25rem",
                fontWeight: 600,
                opacity: 0.8,
              }}
            >
              SMILES
            </span>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              style={{
                width: "100%",
                maxWidth: 480,
                padding: "0.4rem 0.55rem",
                borderRadius: "0.375rem",
                border:
                  "1px solid color-mix(in srgb, currentColor 25%, transparent)",
                background: "transparent",
                color: "inherit",
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                fontSize: "0.8125rem",
              }}
            />
          </label>
        ) : null}

        <PropertyCalculatorBody
          smiles={value}
          properties={propertyList}
          editable={editable}
          showStructure={showStructure}
        />
      </div>
    </RdkitProvider>
  );
}
