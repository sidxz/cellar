"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface CampaignReportConfig {
  imageSize: "small" | "medium" | "large";
  showProperties: { mw: boolean; logP: boolean; hbd: boolean; hba: boolean; tpsa: boolean };
  showDecisionReasonColumn: boolean;
  showNotesColumn: boolean;
  showOverrideStatusColumn: boolean;
}

const DEFAULTS: CampaignReportConfig = {
  imageSize: "small",
  showProperties: { mw: false, logP: false, hbd: false, hba: false, tpsa: false },
  showDecisionReasonColumn: false,
  showNotesColumn: false,
  showOverrideStatusColumn: false,
};

interface Store {
  byCampaign: Record<string, CampaignReportConfig>;
  get: (campaignId: string) => CampaignReportConfig;
  set: (campaignId: string, patch: Partial<CampaignReportConfig>) => void;
  reset: (campaignId: string) => void;
}

export const useReportConfig = create<Store>()(
  persist(
    (set, get) => ({
      byCampaign: {},
      get: (campaignId: string) => get().byCampaign[campaignId] ?? DEFAULTS,
      set: (campaignId, patch) =>
        set((s) => ({
          byCampaign: {
            ...s.byCampaign,
            [campaignId]: { ...(s.byCampaign[campaignId] ?? DEFAULTS), ...patch },
          },
        })),
      reset: (campaignId) =>
        set((s) => {
          const { [campaignId]: _, ...rest } = s.byCampaign;
          return { byCampaign: rest };
        }),
    }),
    {
      name: "campaign-report-config",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
