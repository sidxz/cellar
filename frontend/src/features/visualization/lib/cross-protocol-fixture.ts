import type { Dataset, DatasetColumn } from "../types";

/** A p-potency column of ``protocolId`` as the server sends it at the Compounds level. */
export const pColumn = (key: string, label: string, protocolId: string): DatasetColumn => ({
  key,
  label,
  kind: "number",
  group: label.split(" · ")[0],
  provenance: {
    protocol_id: protocolId,
    readout_definition_id: key.split(":")[1],
    aggregation: "p",
  },
});

/** Protocol A ("Primary") owns the rows; B ("Counter") is compared: m1 tested in both with
 * values, m2 not tested in B, m3 tested in B without a value. */
export const crossProtocol: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 3,
  row_ids: ["m1", "m2", "m3"],
  protocols: [
    { protocol_id: "A", name: "Primary" },
    { protocol_id: "B", name: "Counter" },
  ],
  columns: [
    { key: "compound", label: "Compound", kind: "text", provenance: {} },
    pColumn("dr:x:p", "Primary · pIC50", "A"),
    {
      key: "tested:B",
      label: "Tested in Counter",
      kind: "category",
      group: "Counter",
      provenance: { protocol_id: "B" },
    },
    pColumn("dr:y:p", "Counter · pIC50", "B"),
    {
      key: "sel:dr:x:p|dr:y:p",
      label: "Δ (Primary · pIC50) − (Counter · pIC50)",
      kind: "number",
      unit: "log units",
      group: "Selectivity",
      provenance: { aggregation: "selectivity" },
    },
  ],
  values: {
    compound: ["C1", "C2", "C3"],
    "dr:x:p": [7, 6, 6.5],
    "tested:B": ["Tested", "Not tested", "Tested"],
    "dr:y:p": [5, null, null],
    "sel:dr:x:p|dr:y:p": [2, null, null],
  },
};

/** The same rows loaded from protocol A alone. */
export const singleProtocol: Dataset = {
  ...crossProtocol,
  protocols: [{ protocol_id: "A", name: "Primary" }],
};
