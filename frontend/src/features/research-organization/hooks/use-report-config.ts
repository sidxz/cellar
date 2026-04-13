"use client";

import { create } from "zustand";
import type { ReportConfig, VisibleFields } from "../types";

const DEFAULT_VISIBLE_FIELDS: VisibleFields = {
  structure: ["structure", "registration_number"],
  properties: ["molecular_weight", "logp"],
  collections: false,
  molecule: ["name", "lifecycle_stage"],
  batch: [],
  protocols: {},
  readoutColumns: {},
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
  setReadoutColumns: (protocolId: string, rdDefIds: string[]) => void;
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
  setReadoutColumns: (protocolId, rdDefIds) =>
    set((state) => ({
      config: {
        ...state.config,
        visibleFields: {
          ...state.config.visibleFields,
          readoutColumns: {
            ...state.config.visibleFields.readoutColumns,
            [protocolId]: rdDefIds,
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
          readoutColumns: {
            ...((partial.visibleFields as Partial<VisibleFields> | undefined)?.readoutColumns ?? {}),
          },
        },
      },
    });
  },
  toSavedSearchColumns: () => ({ reportConfig: get().config }),
}));
