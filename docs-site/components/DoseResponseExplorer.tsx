"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type {
  DoseResponseExplorerProps,
  FourPLParams,
} from "./DoseResponseExplorer.impl";

/**
 * DoseResponseExplorer — drag IC50 / Hill slope to see a live 4-parameter
 * logistic curve (Plotly). Client-only.
 */
export const DoseResponseExplorer = dynamic(
  () =>
    import("./DoseResponseExplorer.impl").then((m) => m.DoseResponseExplorerImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="DoseResponseExplorer" />,
  },
);
