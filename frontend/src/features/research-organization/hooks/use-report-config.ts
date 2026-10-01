"use client";

import { create } from "zustand";
import type { ReportConfig, VisibleFields } from "../types";

// Default property columns: Lipinski Rule of Five essentials (MW, LogP, HBD,
// HBA) plus Veber's TPSA. Single-glance druglikeness scan that med-chem users
// recognize. See: doi:10.1016/S0169-409X(96)00423-1 (Lipinski 1997),
// doi:10.1021/jm020017n (Veber 2002).
const DEFAULT_VISIBLE_FIELDS: VisibleFields = {
  structure: ["structure", "registration_number"],
  properties: ["molecular_weight", "logp", "hbd", "hba", "tpsa"],
  molecule: ["name"],
};

const DEFAULT_CONFIG: ReportConfig = {
  imageSize: "medium",
  visibleFields: DEFAULT_VISIBLE_FIELDS,
};

interface ReportConfigState {
  config: ReportConfig;
  updateConfig: (partial: Partial<ReportConfig>) => void;
  setVisibleFields: (fields: Partial<VisibleFields>) => void;
  loadFromSavedSearch: (columns: Record<string, unknown> | null) => void;
}

export const useReportConfig = create<ReportConfigState>((set) => ({
  config: DEFAULT_CONFIG,
  updateConfig: (partial) => set((state) => ({ config: { ...state.config, ...partial } })),
  setVisibleFields: (fields) =>
    set((state) => ({
      config: {
        ...state.config,
        visibleFields: { ...state.config.visibleFields, ...fields },
      },
    })),
  loadFromSavedSearch: (columns) => {
    if (!columns || !columns.reportConfig || typeof columns.reportConfig !== "object") {
      set({ config: DEFAULT_CONFIG });
      return;
    }
    // Saved searches from before the customizer was trimmed carry extra keys
    // (detailLevel, plotScale, batch/protocol fields) — read only what exists.
    const partial = columns.reportConfig as Partial<ReportConfig>;
    set({
      config: {
        imageSize: partial.imageSize ?? DEFAULT_CONFIG.imageSize,
        visibleFields: {
          structure: partial.visibleFields?.structure ?? DEFAULT_VISIBLE_FIELDS.structure,
          properties: partial.visibleFields?.properties ?? DEFAULT_VISIBLE_FIELDS.properties,
          molecule: partial.visibleFields?.molecule ?? DEFAULT_VISIBLE_FIELDS.molecule,
        },
      },
    });
  },
}));
