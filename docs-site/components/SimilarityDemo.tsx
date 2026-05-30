"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type {
  FingerprintType,
  SimilarityDemoProps,
} from "./SimilarityDemo.impl";

/**
 * SimilarityDemo — Tanimoto similarity between two structures via RDKit.js
 * Morgan fingerprints. Client-only.
 */
export const SimilarityDemo = dynamic(
  () => import("./SimilarityDemo.impl").then((m) => m.SimilarityDemoImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="SimilarityDemo" />,
  },
);
