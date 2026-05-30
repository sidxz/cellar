"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type { SmilesAnnotatorProps } from "./SmilesAnnotator.impl";

/**
 * SmilesAnnotator — hover parts of a SMILES string to learn the syntax, with
 * a live structure render. Client-only.
 */
export const SmilesAnnotator = dynamic(
  () => import("./SmilesAnnotator.impl").then((m) => m.SmilesAnnotatorImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="SmilesAnnotator" />,
  },
);
