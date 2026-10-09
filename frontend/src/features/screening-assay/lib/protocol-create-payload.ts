import type { ProtocolFormValues } from "../components/create-protocol/form-values";
import type { CreateConditionDefinitionInput, CreateReadoutDefinitionInput } from "../types";
import { WELL_CONC_X } from "./readout-constants";

/** The create payload's readout definitions from the create form's readout rows (unnamed rows dropped). */
export function readoutDefinitionsPayload(
  readouts: ProtocolFormValues["readouts"],
): CreateReadoutDefinitionInput[] {
  return readouts
    .filter((rd) => rd.name.trim())
    .map((rd) => {
      const base: CreateReadoutDefinitionInput = {
        name: rd.name.trim(),
        data_type: rd.data_type as CreateReadoutDefinitionInput["data_type"],
        unit: rd.unit || null,
        aggregation: rd.aggregation as CreateReadoutDefinitionInput["aggregation"],
        normalizations: rd.normalizations,
        is_calculated: rd.is_calculated,
        calculation_formula: rd.is_calculated ? rd.calculation_formula || null : null,
        display_order: rd.display_order,
      };
      if (rd.data_type === "pick_list") {
        const cleaned = rd.pick_list_values
          .filter((v) => v.label.trim())
          .map((v) => ({ label: v.label.trim(), color: v.color || null }));
        if (cleaned.length > 0) {
          base.pick_list_values = cleaned;
        }
      }
      if (rd.data_type === "dose_response" && rd.dr_y_readout) {
        base.dose_response_config = {
          curve_type: rd.dr_curve_type,
          x_readout_name:
            rd.dr_x_readout === WELL_CONC_X || !rd.dr_x_readout ? null : rd.dr_x_readout,
          y_readout_name: rd.dr_y_readout,
          hill_slope_constraint: rd.dr_hill_constraint,
          activity_threshold: rd.dr_activity_threshold
            ? Number.parseFloat(rd.dr_activity_threshold)
            : null,
          normalization_scope: rd.dr_normalization_scope,
          top_constraint: null,
          bottom_constraint: null,
          // Empty list -> server seeds a single 50% intercept from
          // curve_type. Send only when the chemist explicitly
          // configured >=1 intercept so we don't drown the create
          // payload in a single-default row.
          ...(rd.dr_intercepts.length > 0 ? { intercepts: rd.dr_intercepts } : {}),
        } as CreateReadoutDefinitionInput["dose_response_config"];
      }
      return base;
    });
}

/** The create payload's condition definitions from the create form's condition rows (unnamed rows dropped). */
export function conditionDefinitionsPayload(
  conditions: ProtocolFormValues["conditions"],
): CreateConditionDefinitionInput[] {
  return conditions
    .filter((cd) => cd.name.trim())
    .map((cd) => ({
      name: cd.name.trim(),
      data_type: cd.data_type,
      unit: cd.unit || null,
      ...(cd.data_type === "pick_list" ? { pick_list_values: cd.pick_list_values } : {}),
      ...(cd.fixed_value.trim() ? { fixed_value: cd.fixed_value.trim() } : {}),
    }));
}
