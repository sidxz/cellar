import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import { describe, expect, it } from "vitest";
import {
  formsForCategory,
  mergeFacetDefaults,
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
          },
        },
      ],
    });
    const [signal, ic50] = readoutsFromForm(f);
    expect(signal.normalizations).toEqual(["percent_inhibition"]);
    expect(ic50.unit).toBe("µM");
    expect(ic50.dr_curve_type).toBe("ic50");
    expect(ic50.dr_y_readout).toBe("Signal");
  });
});

describe("mergeFacetDefaults", () => {
  it("fills empty slots only and never replaces a chemist's pick", () => {
    const f = form({
      ontology_defaults: [
        { slot_name: "organism", terms: [MTB] },
        { slot_name: "assay_format", terms: [BAO_BIOCHEM] },
      ],
    });
    const other = { ...MTB, term_id: "ncbi#5833", label: "Plasmodium falciparum" };
    expect(mergeFacetDefaults({ organism: [other] }, f)).toEqual({
      organism: [other],
      assay_format: [BAO_BIOCHEM],
    });
  });

  it("leaves the assay format to the backend when the form follows the target", () => {
    const f = form({
      assay_format_from_target: true,
      ontology_defaults: [{ slot_name: "assay_format", terms: [BAO_BIOCHEM] }],
    });
    expect(mergeFacetDefaults({}, f)).toEqual({});
  });
});
