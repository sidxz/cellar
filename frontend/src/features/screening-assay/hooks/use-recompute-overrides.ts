import { useState } from "react";

export type RecomputeMode = "inherit" | "free" | "range" | "lock";
export type RecomputeHillMode = "inherit" | "enum" | "range";
export type RecomputeHillEnum =
  | "unconstrained"
  | "negative_only"
  | "positive_only"
  | "fixed_at_one";

export interface RecomputeOverrides {
  topMode: RecomputeMode;
  top: string;
  topMin: string;
  topMax: string;
  bottomMode: RecomputeMode;
  bottom: string;
  bottomMin: string;
  bottomMax: string;
  hillMode: RecomputeHillMode;
  hillEnum: RecomputeHillEnum;
  hillMin: string;
  hillMax: string;
}

const DEFAULT_OVERRIDES: RecomputeOverrides = {
  topMode: "inherit",
  top: "",
  topMin: "",
  topMax: "",
  bottomMode: "inherit",
  bottom: "",
  bottomMin: "",
  bottomMax: "",
  hillMode: "inherit",
  hillEnum: "unconstrained",
  hillMin: "",
  hillMax: "",
};

export interface UseRecomputeOverridesReturn {
  overrides: RecomputeOverrides;
  updateOverride: <K extends keyof RecomputeOverrides>(
    field: K,
    value: RecomputeOverrides[K],
  ) => void;
  clearOverrides: () => void;
  /** Build the API payload for a recompute-with-overrides request. */
  buildPayload: () => {
    override_top: boolean;
    top_constraint: number | null;
    top_constraint_min: number | null;
    top_constraint_max: number | null;
    override_bottom: boolean;
    bottom_constraint: number | null;
    bottom_constraint_min: number | null;
    bottom_constraint_max: number | null;
    override_hill: boolean;
    hill_slope_constraint: RecomputeHillEnum | null;
    hill_slope_min: number | null;
    hill_slope_max: number | null;
  };
}

export function useRecomputeOverrides(): UseRecomputeOverridesReturn {
  const [overrides, setOverrides] = useState<RecomputeOverrides>(DEFAULT_OVERRIDES);

  const updateOverride = <K extends keyof RecomputeOverrides>(
    field: K,
    value: RecomputeOverrides[K],
  ) => {
    setOverrides((prev) => ({ ...prev, [field]: value }));
  };

  const clearOverrides = () => setOverrides(DEFAULT_OVERRIDES);

  const buildPayload = () => {
    const parseOrNull = (s: string) => (s !== "" ? Number.parseFloat(s) : null);
    const {
      topMode,
      top,
      topMin,
      topMax,
      bottomMode,
      bottom,
      bottomMin,
      bottomMax,
      hillMode,
      hillEnum,
      hillMin,
      hillMax,
    } = overrides;
    return {
      override_top: topMode !== "inherit",
      top_constraint: topMode === "lock" ? parseOrNull(top) : null,
      top_constraint_min: topMode === "range" ? parseOrNull(topMin) : null,
      top_constraint_max: topMode === "range" ? parseOrNull(topMax) : null,
      override_bottom: bottomMode !== "inherit",
      bottom_constraint: bottomMode === "lock" ? parseOrNull(bottom) : null,
      bottom_constraint_min: bottomMode === "range" ? parseOrNull(bottomMin) : null,
      bottom_constraint_max: bottomMode === "range" ? parseOrNull(bottomMax) : null,
      override_hill: hillMode !== "inherit",
      hill_slope_constraint: hillMode === "enum" ? hillEnum : null,
      hill_slope_min: hillMode === "range" ? parseOrNull(hillMin) : null,
      hill_slope_max: hillMode === "range" ? parseOrNull(hillMax) : null,
    };
  };

  return { overrides, updateOverride, clearOverrides, buildPayload };
}
