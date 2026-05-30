"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type {
  PropertyCalculatorProps,
  PropertyKey,
} from "./PropertyCalculator.impl";

/**
 * PropertyCalculator — SMILES in, live RDKit descriptors out
 * (MW, logP, TPSA, HBD, HBA, …). Client-only.
 */
export const PropertyCalculator = dynamic(
  () => import("./PropertyCalculator.impl").then((m) => m.PropertyCalculatorImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="PropertyCalculator" />,
  },
);
