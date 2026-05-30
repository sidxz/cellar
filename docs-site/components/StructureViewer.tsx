"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type { StructureViewerProps } from "./StructureViewer.impl";

/**
 * StructureViewer — input/select a SMILES and render its 2D structure.
 * Client-only (RDKit.js WASM needs the browser).
 */
export const StructureViewer = dynamic(
  () => import("./StructureViewer.impl").then((m) => m.StructureViewerImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="StructureViewer" />,
  },
);
