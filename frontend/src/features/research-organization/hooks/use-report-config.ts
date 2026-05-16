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
  collections: false,
  molecule: ["name", "lifecycle_stage"],
  batch: [],
  protocols: {},
};

const DEFAULT_CONFIG: ReportConfig = {
  detailLevel: "summary",
  plotScale: "per_molecule",
  showPlotLegend: false,
  imageSize: "medium",
  columnWidth: 25,
  visibleFields: DEFAULT_VISIBLE_FIELDS,
};

interface ReportConfigState {
  config: ReportConfig;
  setConfig: (config: ReportConfig) => void;
  updateConfig: (partial: Partial<ReportConfig>) => void;
  setVisibleFields: (fields: Partial<VisibleFields>) => void;
  setProtocolFields: (protocolId: string, fields: string[]) => void;
  resetToDefaults: () => void;
  loadFromSavedSearch: (columns: Record<string, unknown> | null) => void;
  toSavedSearchColumns: () => Record<string, unknown>;
}

export const useReportConfig = create<ReportConfigState>((set, get) => ({
  config: DEFAULT_CONFIG,
  setConfig: (config) => set({ config }),
  updateConfig: (partial) =>
    set((state) => ({ config: { ...state.config, ...partial } })),
  setVisibleFields: (fields) =>
    set((state) => ({
      config: {
        ...state.config,
        visibleFields: { ...state.config.visibleFields, ...fields },
      },
    })),
  setProtocolFields: (protocolId, fields) =>
    set((state) => ({
      config: {
        ...state.config,
        visibleFields: {
          ...state.config.visibleFields,
          protocols: {
            ...state.config.visibleFields.protocols,
            [protocolId]: fields,
          },
        },
      },
    })),
  resetToDefaults: () => set({ config: DEFAULT_CONFIG }),
  loadFromSavedSearch: (columns) => {
    if (!columns || !columns.reportConfig || typeof columns.reportConfig !== "object") {
      set({ config: DEFAULT_CONFIG });
      return;
    }
    const partial = columns.reportConfig as Partial<ReportConfig>;
    set({
      config: {
        ...DEFAULT_CONFIG,
        ...partial,
        visibleFields: {
          ...DEFAULT_VISIBLE_FIELDS,
          ...(partial.visibleFields ?? {}),
          protocols: {
            ...((partial.visibleFields as Partial<VisibleFields> | undefined)?.protocols ?? {}),
          },
        },
      },
    });
  },
  toSavedSearchColumns: () => ({ reportConfig: get().config }),
}));
