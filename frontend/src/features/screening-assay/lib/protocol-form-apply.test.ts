import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import { describe, expect, it } from "vitest";
import {
  applyFormFacets,
  conditionsFromForm,
  formsForCategory,
  pickFormForCategory,
  readoutsFromForm,
} from "./protocol-form-apply";

const form = (over: Partial<ProtocolForm>): ProtocolForm =>
  ({
    id: crypto.randomUUID(),
    workspace_id: "w",
    name: "f",
    is_default: false,
    category_id: null,
    assay_format_from_target: false,
    readout_templates: [
      {
        name: "Signal",
        data_type: "numeric",
        aggregation: "none",
        normalization: "none",
        is_calculated: false,
      },
    ],
    condition_templates: null,
    ontology_defaults: null,
    version: 1,
    ...over,
  }) as ProtocolForm;

const BAO_BIOCHEM = {
  term_id: "bao#BAO_0000217",
  label: "biochemical format",
  ontology_source: "BAO",
  uri: null,
};
const MTB = {
  term_id: "ncbi#1773",
  label: "Mycobacterium tuberculosis",
  ontology_source: "NCBITAXON",
  uri: null,
};

describe("pickFormForCategory", () => {
  it("prefers the category's default, then its only form, then the generic default", () => {
    const a = form({ category_id: "c1" });
    const b = form({ category_id: "c1", is_default: true });
    const g = form({ is_default: true });
    expect(pickFormForCategory([a, b, g], "c1")).toBe(b);
    expect(pickFormForCategory([a, g], "c1")).toBe(a);
    expect(pickFormForCategory([g], "c2")).toBe(g);
  });

  it("asks (null) when the category has several forms and no default", () => {
    const a = form({ category_id: "c1" });
    const b = form({ category_id: "c1" });
    expect(pickFormForCategory([a, b, form({ is_default: true })], "c1")).toBeNull();
    expect(formsForCategory([a, b], "c1").own).toHaveLength(2);
  });
});

describe("readoutsFromForm", () => {
  it("carries every template field, including dose-response config", () => {
    const f = form({
      readout_templates: [
        {
          name: "Signal",
          data_type: "numeric",
          normalization: "percent_inhibition",
          aggregation: "none",
          is_calculated: false,
        },
        {
          name: "IC50",
          data_type: "dose_response",
          unit: "µM",
          aggregation: "none",
          normalization: "none",
          is_calculated: false,
          dose_response_config: {
            curve_type: "ic50",
            y_readout_name: "Signal",
            hill_slope_constraint: "unconstrained",
            intercepts: [
              { kind: "ic", level: 50, basis: "relative_percent" },
              { kind: "ic", level: 90, basis: "relative_percent", label: "IC90" },
            ],
          },
        },
      ],
    });
    const [signal, ic50] = readoutsFromForm(f);
    expect(signal.normalizations).toEqual(["percent_inhibition"]);
    expect(ic50.unit).toBe("µM");
    expect(ic50.dr_curve_type).toBe("ic50");
    expect(ic50.dr_y_readout).toBe("Signal");
    expect(ic50.dr_intercepts).toEqual([
      { kind: "ic", level: 50, basis: "relative_percent" },
      { kind: "ic", level: 90, basis: "relative_percent", label: "IC90" },
    ]);
    expect(signal.dr_intercepts).toEqual([]);
  });
});

describe("applyFormFacets", () => {
  const BAO_CELL = { ...BAO_BIOCHEM, term_id: "bao#BAO_0000219", label: "cell based format" };
  const withFormat = (terms: (typeof BAO_BIOCHEM)[], over: Partial<ProtocolForm> = {}) =>
    form({ ontology_defaults: [{ slot_name: "assay_format", terms }], ...over });

  it("fills empty slots only and never replaces a chemist's pick", () => {
    const f = form({
      ontology_defaults: [
        { slot_name: "organism", terms: [MTB] },
        { slot_name: "assay_format", terms: [BAO_BIOCHEM] },
      ],
    });
    const other = { ...MTB, term_id: "ncbi#5833", label: "Plasmodium falciparum" };
    expect(applyFormFacets({ organism: [other] }, {}, f)).toEqual({
      annotations: { organism: [other], assay_format: [BAO_BIOCHEM] },
      applied: { assay_format: JSON.stringify([BAO_BIOCHEM]) },
    });
  });

  it("replaces what the last form applied, and clears it when the new form has none", () => {
    const first = applyFormFacets({}, {}, withFormat([BAO_BIOCHEM]));
    const second = applyFormFacets(first.annotations, first.applied, withFormat([BAO_CELL]));
    expect(second.annotations).toEqual({ assay_format: [BAO_CELL] });
    expect(applyFormFacets(second.annotations, second.applied, form({})).annotations).toEqual({});
    expect(applyFormFacets(second.annotations, second.applied, null).annotations).toEqual({});
  });

  it("keeps a slot the chemist changed after a form filled it", () => {
    const first = applyFormFacets({}, {}, withFormat([BAO_BIOCHEM]));
    const edited = { assay_format: [BAO_CELL] };
    expect(applyFormFacets(edited, first.applied, null)).toEqual({
      annotations: edited,
      applied: {},
    });
  });

  it("leaves the assay format to the backend when the form follows the target", () => {
    const first = applyFormFacets({}, {}, withFormat([BAO_BIOCHEM]));
    const follows = withFormat([BAO_CELL], { assay_format_from_target: true });
    expect(applyFormFacets({}, {}, follows).annotations).toEqual({});
    // A format the last form applied is dropped, too.
    expect(applyFormFacets(first.annotations, first.applied, follows).annotations).toEqual({});
  });
});

describe("conditionsFromForm", () => {
  it("carries a pick-list condition's values", () => {
    const f = form({
      condition_templates: [
        { name: "S9", data_type: "pick_list", unit: null, pick_list_values: ["with", "without"] },
        { name: "Time", data_type: "numeric", unit: "h" },
      ],
    });
    expect(conditionsFromForm(f)).toEqual([
      { name: "S9", data_type: "pick_list", unit: "", pick_list_values: ["with", "without"] },
      { name: "Time", data_type: "numeric", unit: "h", pick_list_values: [] },
    ]);
  });
});
