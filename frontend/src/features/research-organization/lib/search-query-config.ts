import type {
  ActivityCriterion,
  BatchCriterion,
  BatchFieldType,
  CollectionCriterion,
  CustomFieldCriterion,
  CustomFieldMode,
  GroupCriterion,
  KeywordListCriterion,
  ProjectCriterion,
  PropertyCriterion,
  PropertyOperator,
  RefType,
  RunDateCriterion,
  SelectivityCriterion,
  StructureCriterion,
  StructureSearchType,
  TextCriterion,
  TextOperator,
} from "../types";

// ─── Field / operator options ────────────────────────────────────────────────

export const TEXT_FIELDS = [
  { value: "name", label: "Name" },
  { value: "registration_number", label: "Registration Number" },
  { value: "molecular_formula", label: "Molecular Formula" },
  { value: "inchi_key", label: "InChI Key" },
] as const;

export const TEXT_OPERATORS: { value: TextOperator; label: string }[] = [
  { value: "contains", label: "Contains" },
  { value: "equals", label: "Equals" },
  { value: "starts_with", label: "Starts With" },
];

export const PROPERTY_FIELDS = [
  { value: "molecular_weight", label: "Molecular Weight" },
  { value: "logp", label: "LogP" },
  { value: "tpsa", label: "TPSA" },
  { value: "hbd", label: "HBD" },
  { value: "hba", label: "HBA" },
  { value: "rotatable_bonds", label: "Rotatable Bonds" },
  { value: "heavy_atom_count", label: "Heavy Atom Count" },
  { value: "aromatic_rings", label: "Aromatic Rings" },
  { value: "ring_count", label: "Ring Count" },
  { value: "ro5_violations", label: "Ro5 Violations" },
] as const;

export const PROPERTY_OPERATORS: { value: PropertyOperator; label: string }[] = [
  { value: "eq", label: "=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "between", label: "Between" },
];

export const STRUCTURE_TYPES: { value: StructureSearchType; label: string }[] = [
  { value: "substructure", label: "Substructure (SMARTS)" },
  { value: "similarity", label: "Similarity (SMILES)" },
  { value: "exact", label: "Exact (InChIKey)" },
];

export const BATCH_TEXT_FIELDS = [
  { value: "batch_number", label: "Batch Number" },
  { value: "source", label: "Source" },
  { value: "salt_name", label: "Salt Form" },
  { value: "vendor_catalog_number", label: "Vendor Catalog #" },
  { value: "notebook_reference", label: "Notebook Reference" },
] as const;

export const BATCH_NUMERIC_FIELDS = [
  { value: "purity", label: "Purity (%)" },
  { value: "amount_value", label: "Amount" },
] as const;

export const BATCH_FIELD_TYPE_OPTIONS: { value: BatchFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "numeric", label: "Numeric" },
  { value: "date", label: "Synthesis Date" },
];

export const CURVE_TYPE_OPTIONS = [
  { value: "ic50", label: "IC50" },
  { value: "ec50", label: "EC50" },
  { value: "ki", label: "Ki" },
  { value: "kd", label: "Kd" },
] as const;

export const REF_TYPE_OPTIONS: { value: RefType; label: string }[] = [
  { value: "registration_number", label: "Registration Number" },
  { value: "name", label: "Name" },
  { value: "external_id", label: "External ID" },
  { value: "smiles", label: "SMILES" },
  { value: "inchi_key", label: "InChI Key" },
];

export const CUSTOM_FIELD_MODE_OPTIONS: { value: CustomFieldMode; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "numeric", label: "Numeric" },
];

// ─── Default criterion factories ─────────────────────────────────────────────

export function defaultTextCriterion(): TextCriterion {
  return { type: "text", field: "name", operator: "contains", value: "" };
}

export function defaultPropertyCriterion(): PropertyCriterion {
  return {
    type: "property",
    field: "molecular_weight",
    operator: "gte",
    value: undefined,
    min: undefined,
    max: undefined,
  };
}

export function defaultStructureCriterion(): StructureCriterion {
  return {
    type: "structure",
    search_type: "substructure",
    smarts: "",
    smiles: undefined,
    threshold: 0.7,
    inchi_key: undefined,
  };
}

export function defaultActivityCriterion(): ActivityCriterion {
  return { type: "activity", protocol_id: "", operator: "lt" as PropertyOperator, value: 0 };
}

export function defaultCollectionCriterion(): CollectionCriterion {
  return { type: "collection", collection_id: "" };
}

export function defaultKeywordListCriterion(): KeywordListCriterion {
  return { type: "keyword_list", values: [], ref_type: "registration_number" as RefType };
}

export function defaultRunDateCriterion(): RunDateCriterion {
  return { type: "run_date" };
}

export function defaultBatchCriterion(): BatchCriterion {
  return {
    type: "batch",
    field_type: "text",
    field: "batch_number",
    operator: "contains",
    value: "",
  };
}

export function defaultProjectCriterion(): ProjectCriterion {
  return { type: "project", project_ids: [] };
}

export function defaultGroupCriterion(): GroupCriterion {
  return { type: "group", logic: "or", criteria: [] };
}

export function defaultCustomFieldCriterion(): CustomFieldCriterion {
  return { type: "custom_field", field: "", mode: "text", operator: "contains", value: "" };
}

export function defaultSelectivityCriterion(): SelectivityCriterion {
  return {
    type: "selectivity",
    target_protocol_id: "",
    target_curve_type: "ic50",
    counter_protocol_id: "",
    counter_curve_type: "ic50",
    ratio_operator: "gte",
    ratio_value: 100,
  };
}
