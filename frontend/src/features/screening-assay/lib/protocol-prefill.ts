import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import { type ProtocolFormValues, defaultReadout } from "../components/create-protocol/form-values";
import type { Protocol, ProtocolReference } from "../types";
import { paperLevelReferences } from "./protocol-references";
import { WELL_CONC_X } from "./readout-constants";

export interface ProtocolPrefill {
  values: ProtocolFormValues;
  ontologyAnnotations: Record<string, OntologyTerm[]>;
  references: ProtocolReference[];
}

/** What a new protocol starts with when it is made from an existing one: the facts, the form,
 *  the conditions (pick lists and fixed values) and the paper-level references. Never the
 *  discriminator (the new assay's own), nicknames or the assay-level ids (P7). */
export function prefillFromProtocol(p: Protocol): ProtocolPrefill {
  return {
    values: {
      protocol_type: p.protocol_type,
      discriminator: "",
      target_ids: (p.targets ?? []).map((t) => t.id),
      category: p.category ?? "",
      description: p.description ?? "",
      dose_unit: p.dose_unit,
      readouts: p.readout_definitions.map((rd, i) => {
        const dr = rd.dose_response_config;
        return {
          ...defaultReadout(i + 1),
          name: rd.name,
          data_type: rd.data_type,
          unit: rd.unit ?? "",
          aggregation: rd.aggregation ?? "none",
          normalizations: rd.normalizations ?? [],
          is_calculated: rd.is_calculated,
          calculation_formula: rd.calculation_formula ?? "",
          display_order: rd.display_order ?? i + 1,
          pick_list_values: rd.pick_list_values ?? [],
          ...(dr
            ? {
                dr_curve_type: dr.curve_type,
                dr_x_readout: dr.x_readout_name ?? WELL_CONC_X,
                dr_y_readout: dr.y_readout_name,
                dr_hill_constraint: dr.hill_slope_constraint,
                dr_normalization_scope: dr.normalization_scope,
                dr_activity_threshold:
                  dr.activity_threshold != null ? String(dr.activity_threshold) : "",
                dr_intercepts: dr.intercepts ?? [],
              }
            : {}),
        };
      }),
      conditions: p.condition_definitions.map((cd) => ({
        name: cd.name,
        data_type: cd.data_type,
        unit: cd.unit ?? "",
        pick_list_values: cd.pick_list_values ?? [],
        fixed_value: cd.fixed_value ?? "",
      })),
    },
    ontologyAnnotations: p.ontology_annotations ?? {},
    references: paperLevelReferences(p.references ?? []),
  };
}
