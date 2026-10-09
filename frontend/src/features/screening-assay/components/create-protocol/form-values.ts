import { z } from "zod";
import { WELL_CONC_X } from "../../lib/readout-constants";
import type { DoseUnit, InterceptSpec, PickListValue, ReadoutNormalization } from "../../types";

// ---------------------------------------------------------------------------
// Zod schemas
// ---------------------------------------------------------------------------

export const readoutSchema = z.object({
  name: z.string(),
  data_type: z.string(),
  unit: z.string(),
  aggregation: z.string(),
  normalizations: z.array(z.string()) as z.ZodArray<z.ZodType<ReadoutNormalization>>,
  is_calculated: z.boolean(),
  calculation_formula: z.string(),
  display_order: z.number(),
  pick_list_values: z.array(
    z.object({ label: z.string(), color: z.string().nullable().optional() }),
  ) as z.ZodArray<z.ZodType<PickListValue>>,
  dr_curve_type: z.string(),
  dr_x_readout: z.string(),
  dr_y_readout: z.string(),
  dr_hill_constraint: z.string(),
  dr_normalization_scope: z.string(),
  dr_activity_threshold: z.string(),
  // Per-spec intercepts derived from the same Hill fit. Empty defaults
  // server-side to a single 50% intercept seeded from `dr_curve_type`.
  dr_intercepts: z.array(
    z.object({
      kind: z.enum(["ic", "ec"]),
      level: z.number(),
      basis: z.enum(["relative_percent", "absolute"]),
      label: z.string().nullable().optional(),
    }),
  ) as z.ZodArray<z.ZodType<InterceptSpec>>,
});

export const conditionSchema = z.object({
  name: z.string(),
  data_type: z.string(),
  unit: z.string(),
});

export const protocolSchema = z.object({
  protocol_type: z.string(),
  discriminator: z.string(),
  target_ids: z.array(z.string()),
  category: z.string(),
  description: z.string(),
  dose_unit: z.string() as z.ZodType<DoseUnit>,
  readouts: z.array(readoutSchema),
  conditions: z.array(conditionSchema),
});

export type ProtocolFormValues = z.infer<typeof protocolSchema>;

// ---------------------------------------------------------------------------
// Default factories
// ---------------------------------------------------------------------------

export function defaultReadout(order: number): ProtocolFormValues["readouts"][number] {
  return {
    name: "",
    data_type: "numeric",
    unit: "",
    aggregation: "none",
    normalizations: [],
    is_calculated: false,
    calculation_formula: "",
    display_order: order,
    pick_list_values: [],
    dr_curve_type: "ic50",
    dr_x_readout: WELL_CONC_X,
    dr_y_readout: "",
    dr_hill_constraint: "unconstrained",
    dr_normalization_scope: "per_plate",
    dr_activity_threshold: "",
    dr_intercepts: [],
  };
}

export function defaultCondition(): ProtocolFormValues["conditions"][number] {
  return { name: "", data_type: "text", unit: "" };
}

export const DEFAULT_VALUES: ProtocolFormValues = {
  protocol_type: "biochemical",
  discriminator: "",
  target_ids: [],
  category: "",
  description: "",
  dose_unit: "uM",
  readouts: [defaultReadout(1)],
  conditions: [],
};
