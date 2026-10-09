import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import {
  type ProtocolFormValues,
  defaultCondition,
  defaultReadout,
} from "../components/create-protocol/form-values";
import type { PickListValue, ReadoutNormalization } from "../types";
import { WELL_CONC_X } from "./readout-constants";

export function formsForCategory(forms: ProtocolForm[], categoryId: string | null) {
  return {
    own: categoryId ? forms.filter((f) => f.category_id === categoryId) : [],
    generic: forms.filter((f) => !f.category_id),
  };
}

/** The category's default, its only form, or (when it has none) the generic default; null means "ask". */
export function pickFormForCategory(
  forms: ProtocolForm[],
  categoryId: string | null,
): ProtocolForm | null {
  const { own, generic } = formsForCategory(forms, categoryId);
  const ownDefault = own.find((f) => f.is_default);
  if (ownDefault) return ownDefault;
  if (own.length === 1) return own[0];
  if (own.length === 0) return generic.find((f) => f.is_default) ?? null;
  return null;
}

export function readoutsFromForm(form: ProtocolForm): ProtocolFormValues["readouts"] {
  return form.readout_templates.map((tpl, i) => {
    const norm =
      tpl.normalization && tpl.normalization !== "none"
        ? [tpl.normalization as ReadoutNormalization]
        : [];
    const dr = tpl.dose_response_config as Record<string, unknown> | null | undefined;
    return {
      ...defaultReadout(i + 1),
      name: tpl.name,
      data_type: tpl.data_type,
      unit: tpl.unit ?? "",
      aggregation: tpl.aggregation ?? "none",
      normalizations: norm,
      is_calculated: tpl.is_calculated ?? false,
      calculation_formula: tpl.calculation_formula ?? "",
      pick_list_values: ((tpl.pick_list_values ?? []) as Array<PickListValue | string>).map((v) =>
        typeof v === "string" ? { label: v } : v,
      ),
      ...(dr
        ? {
            dr_curve_type: String(dr.curve_type ?? "ic50"),
            dr_x_readout: (dr.x_readout_name as string | null) ?? WELL_CONC_X,
            dr_y_readout: String(dr.y_readout_name ?? ""),
            dr_hill_constraint: String(dr.hill_slope_constraint ?? "unconstrained"),
            dr_normalization_scope: String(dr.normalization_scope ?? "per_plate"),
            dr_activity_threshold:
              dr.activity_threshold != null ? String(dr.activity_threshold) : "",
          }
        : {}),
    };
  });
}

export function conditionsFromForm(form: ProtocolForm): ProtocolFormValues["conditions"] {
  return (form.condition_templates ?? []).map((tpl) => ({
    ...defaultCondition(),
    name: tpl.name,
    data_type: tpl.data_type,
    unit: tpl.unit ?? "",
  }));
}

/** Fills only empty slots, so a chemist's pick is never replaced. */
export function mergeFacetDefaults(
  current: Record<string, OntologyTerm[]>,
  form: ProtocolForm,
): Record<string, OntologyTerm[]> {
  const next = { ...current };
  for (const d of form.ontology_defaults ?? []) {
    if (d.slot_name === "assay_format" && form.assay_format_from_target) continue;
    if ((next[d.slot_name] ?? []).length > 0) continue;
    next[d.slot_name] = (d.terms ?? []).map((t) => ({
      term_id: String(t.term_id ?? ""),
      label: String(t.label ?? ""),
      ontology_source: String(t.ontology_source ?? ""),
      uri: (t.uri as string | null) ?? null,
    }));
  }
  return next;
}
