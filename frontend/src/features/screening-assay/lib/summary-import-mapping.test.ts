import { describe, expect, it } from "vitest";
import type { SummaryHeaderSuggestionModel } from "../hooks/use-summary-import";
import { buildMapping, suggestionsToDraft } from "./summary-import-mapping";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function suggestion(
  partial: Partial<SummaryHeaderSuggestionModel> & { header: string; role: string },
): SummaryHeaderSuggestionModel {
  return {
    confidence: "high",
    ...partial,
  };
}

// ─── suggestionsToDraft ───────────────────────────────────────────────────────

describe("suggestionsToDraft", () => {
  it("maps roles and binds readout defs", () => {
    const draft = suggestionsToDraft([
      suggestion({ header: "Compound", role: "compound_ref" }),
      suggestion({
        header: "IC50",
        role: "readout",
        readout_definition_id: "def-1",
      }),
    ]);

    expect(draft.roles).toEqual({
      Compound: "compound_ref",
      IC50: "readout",
    });
    expect(draft.readoutDefByHeader).toEqual({ IC50: "def-1" });
  });

  it("does NOT bind a readout suggestion with null/missing readout_definition_id", () => {
    const draft = suggestionsToDraft([
      suggestion({ header: "IC50", role: "readout", readout_definition_id: null }),
      suggestion({ header: "Ki", role: "readout" }),
    ]);

    expect(draft.roles).toEqual({ IC50: "readout", Ki: "readout" });
    expect(draft.readoutDefByHeader).toEqual({});
  });
});

// ─── buildMapping ─────────────────────────────────────────────────────────────

describe("buildMapping", () => {
  it("returns a valid mapping for compound_ref + one bound readout", () => {
    const mapping = buildMapping({
      roles: { Compound: "compound_ref", IC50: "readout", Notes: "ignore" },
      readoutDefByHeader: { IC50: "def-1" },
    });

    expect(mapping).toEqual({
      compound_ref: "Compound",
      batch_ref: null,
      readout_columns: { IC50: "def-1" },
    });
  });

  it("returns null when a readout column is unbound", () => {
    const mapping = buildMapping({
      roles: { Compound: "compound_ref", IC50: "readout" },
      readoutDefByHeader: {},
    });

    expect(mapping).toBeNull();
  });

  it("returns null when there is no compound_ref AND no batch_ref", () => {
    const mapping = buildMapping({
      roles: { IC50: "readout", Notes: "ignore" },
      readoutDefByHeader: { IC50: "def-1" },
    });

    expect(mapping).toBeNull();
  });

  it("returns null when there are no readout columns", () => {
    const mapping = buildMapping({
      roles: { Compound: "compound_ref", Notes: "ignore" },
      readoutDefByHeader: {},
    });

    expect(mapping).toBeNull();
  });

  it("works with batch_ref instead of compound_ref", () => {
    const mapping = buildMapping({
      roles: { Batch: "batch_ref", IC50: "readout" },
      readoutDefByHeader: { IC50: "def-1" },
    });

    expect(mapping).toEqual({
      compound_ref: null,
      batch_ref: "Batch",
      readout_columns: { IC50: "def-1" },
    });
  });
});
