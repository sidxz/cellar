# chemcellar Docs — Interactive Widgets Reference

Six client-only chemistry widgets ship with the docs site. They are registered
globally in `mdx-components.tsx`, so **you can use them in any `.mdx` page
without importing anything**.

All widgets are **client-only** (`next/dynamic`, `ssr: false`) because
RDKit.js (WASM), Ketcher, and Plotly need the browser. RDKit-backed widgets are
wrapped in a shared `RdkitProvider` that loads the WASM module once per page.

> The prop signatures below are the **contract**. Widget-builder agents implement
> against these exact signatures; content writers embed against them. They are
> final — do not change a signature without updating this file and both sides.

| Widget | Does | Import path |
|---|---|---|
| `StructureViewer` | Input/select a SMILES → render a 2D structure | `@/components/StructureViewer` |
| `PropertyCalculator` | SMILES → live MW/logP/TPSA/HBD/HBA | `@/components/PropertyCalculator` |
| `DoseResponseExplorer` | Drag IC50 / Hill slope → live 4PL curve | `@/components/DoseResponseExplorer` |
| `PlateHeatmapDemo` | Interactive 96/384-well plate, hover wells | `@/components/PlateHeatmapDemo` |
| `SimilarityDemo` | Tanimoto between two structures | `@/components/SimilarityDemo` |
| `SmilesAnnotator` | Hover parts of a SMILES to learn syntax | `@/components/SmilesAnnotator` |

Supporting modules:

- `@/components/RdkitProvider` — `RdkitProvider` (context) + `useRdkit()` hook.
- `@/components/rdkit-loader` — `getRDKit(): Promise<RDKitModule>` singleton.

---

## StructureViewer

Input or select a SMILES string and render its 2D structure via RDKit.js.

**Import:** `@/components/StructureViewer`

```ts
export interface StructureViewerProps {
  /** SMILES (or CXSMILES) to render. When omitted, the widget shows an input. */
  smiles?: string;
  /** Render width in pixels. */
  width?: number;          // default 320
  /** Render height in pixels. */
  height?: number;         // default 220
  /** Optional SMARTS pattern to highlight matching atoms/bonds. */
  highlightSmarts?: string;
  /** Allow the reader to type/paste their own SMILES. */
  editable?: boolean;      // default true
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<StructureViewer smiles="CC(=O)Oc1ccccc1C(=O)O" />
```

---

## PropertyCalculator

SMILES in, live RDKit-computed descriptors out (MW, logP, TPSA, HBD, HBA, …).

**Import:** `@/components/PropertyCalculator`

```ts
export type PropertyKey =
  | "mw" | "logp" | "tpsa" | "hbd" | "hba"
  | "rotatableBonds" | "rings" | "formula";

export interface PropertyCalculatorProps {
  /** Initial SMILES. When omitted, the widget shows an input. */
  smiles?: string;
  /** Which descriptors to display. */
  properties?: PropertyKey[];   // default ["mw","logp","tpsa","hbd","hba"]
  /** Allow the reader to edit the SMILES. */
  editable?: boolean;           // default true
  /** Show the 2D structure alongside the property table. */
  showStructure?: boolean;      // default true
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<PropertyCalculator smiles="CC(=O)Oc1ccccc1C(=O)O" />
```

---

## DoseResponseExplorer

Drag IC50 / Hill slope to see a live four-parameter logistic (4PL) curve,
mirroring the screening dose-response chart (Plotly).

**Import:** `@/components/DoseResponseExplorer`

```ts
export interface FourPLParams {
  /** Bottom asymptote (% response at high concentration / low dose). */
  bottom: number;
  /** Top asymptote (% response at zero dose). */
  top: number;
  /** Inflection point: IC50 / EC50 in molar units. */
  ic50: number;
  /** Hill slope (steepness of the transition). */
  hillSlope: number;
}

export interface DoseResponseExplorerProps {
  /** Initial 4PL parameters. Sensible defaults applied when omitted. */
  initial?: Partial<FourPLParams>;
  /** Which parameters the reader may drag/edit. */
  adjustable?: (keyof FourPLParams)[];   // default ["ic50","hillSlope"]
  /** Concentration axis bounds in molar [min, max]. */
  concentrationRange?: [number, number]; // default [1e-10, 1e-4]
  /** Show the IC50/EC50 + Hill slope readout below the chart. */
  showReadout?: boolean;                 // default true
  /** Chart height in pixels. */
  height?: number;                       // default 320
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<DoseResponseExplorer initial={{ ic50: 1e-7, hillSlope: 1 }} />
```

---

## PlateHeatmapDemo

Interactive 96/384-well microplate heatmap with per-well hover, mirroring the
screening plate-readout pattern.

**Import:** `@/components/PlateHeatmapDemo`

```ts
export type PlateFormat = 96 | 384;

export interface WellValue {
  /** Well address, e.g. "A1". */
  well: string;
  /** Numeric readout used for the heatmap color. */
  value: number;
  /** Optional label shown on hover. */
  label?: string;
}

export interface PlateHeatmapDemoProps {
  /** Plate format. */
  format?: PlateFormat;        // default 96
  /** Well values. When omitted, the widget generates a sample gradient. */
  wells?: WellValue[];
  /** Color scale name (Plotly/named ramp). */
  colorScale?: string;         // default "viridis"
  /** Show the row/column axis labels. */
  showLabels?: boolean;        // default true
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<PlateHeatmapDemo format={96} />
```

---

## SimilarityDemo

Tanimoto similarity between two structures via RDKit.js Morgan fingerprints,
with both structures rendered.

**Import:** `@/components/SimilarityDemo`

```ts
export type FingerprintType = "morgan" | "rdkit" | "pattern";

export interface SimilarityDemoProps {
  /** Initial SMILES for the left/reference structure. */
  smilesA?: string;
  /** Initial SMILES for the right/query structure. */
  smilesB?: string;
  /** Fingerprint algorithm. */
  fingerprint?: FingerprintType;  // default "morgan"
  /** Morgan radius (when fingerprint = "morgan"). */
  radius?: number;                // default 2
  /** Allow the reader to edit both SMILES. */
  editable?: boolean;             // default true
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<SimilarityDemo
  smilesA="CC(=O)Oc1ccccc1C(=O)O"
  smilesB="CC(=O)Nc1ccc(O)cc1"
/>
```

---

## SmilesAnnotator

Hover parts of a SMILES string to learn the syntax (atoms, bonds, rings,
branches, stereo), with a live RDKit.js render.

**Import:** `@/components/SmilesAnnotator`

```ts
export interface SmilesAnnotatorProps {
  /** SMILES string to break down and annotate. Required. */
  smiles: string;
  /** Show the rendered 2D structure beside the annotated string. */
  showStructure?: boolean;            // default true
  /**
   * Optional explicit annotations keyed by token (or token index) — overrides
   * the built-in syntax descriptions for teaching purposes.
   */
  annotations?: Record<string, string>;
  /** Extra CSS class for the outer container. */
  className?: string;
}
```

**Usage:**

```mdx
<SmilesAnnotator smiles="C[C@@H](N)C(=O)O" />
```
