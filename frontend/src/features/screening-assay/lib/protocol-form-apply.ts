import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import {
  type ProtocolFormValues,
  defaultCondition,
  defaultReadout,
} from "../components/create-protocol/form-values";
import type { InterceptSpec, PickListValue, ReadoutNormalization } from "../types";
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
            dr_intercepts: (dr.intercepts as InterceptSpec[] | undefined) ?? [],
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
    pick_list_values: tpl.pick_list_values ?? [],
  }));
}

/** The facet terms a form brings; none for the assay format when it follows the target. */
function formFacets(form: ProtocolForm | null): Record<string, OntologyTerm[]> {
  const out: Record<string, OntologyTerm[]> = {};
  for (const d of form?.ontology_defaults ?? []) {
    if (d.slot_name === "assay_format" && form?.assay_format_from_target) continue;
    const terms = (d.terms ?? []).map((t) => ({
      term_id: String(t.term_id ?? ""),
      label: String(t.label ?? ""),
      ontology_source: String(t.ontology_source ?? ""),
      uri: (t.uri as string | null) ?? null,
    }));
    if (terms.length > 0) out[d.slot_name] = terms;
  }
  return out;
}

/**
 * Applies a form's facet defaults (null: no form). A slot that is empty, or still holds what the
 * last form applied, gets the new form's terms, or is cleared when the new form has none. A slot
 * the chemist filled is left alone. `lastApplied` and the returned `applied` map slot → the JSON
 * of the terms a form put there.
 */
export function applyFormFacets(
  current: Record<string, OntologyTerm[]>,
  lastApplied: Record<string, string>,
  form: ProtocolForm | null,
): { annotations: Record<string, OntologyTerm[]>; applied: Record<string, string> } {
  const annotations = { ...current };
  const applied: Record<string, string> = {};
  const incoming = formFacets(form);
  for (const slot of new Set([...Object.keys(lastApplied), ...Object.keys(incoming)])) {
    const now = JSON.stringify(annotations[slot] ?? []);
    if (now !== "[]" && now !== lastApplied[slot]) continue;
    const terms = incoming[slot];
    if (terms) {
      annotations[slot] = terms;
      applied[slot] = JSON.stringify(terms);
    } else {
      delete annotations[slot];
    }
  }
  return { annotations, applied };
}
