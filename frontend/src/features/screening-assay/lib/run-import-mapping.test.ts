import { describe, expect, it } from "vitest";
import type { RunImportTemplate } from "../hooks/use-run-import";
import {
  applyTemplateToDraft,
  emptyDraft,
  pickBestTemplate,
  suggestionToInitialDraft,
} from "./run-import-mapping";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeTemplate(id: string, mapping: Record<string, unknown>): RunImportTemplate {
  return {
    id,
    workspace_id: "ws-1",
    name: `template-${id}`,
    description: null,
    column_mapping: mapping,
    created_by: "user-1",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  };
}

// ─── applyTemplateToDraft ─────────────────────────────────────────────────────

describe("applyTemplateToDraft", () => {
  it("overwrites fields specified by the template when the header is present", () => {
    const draft = emptyDraft();
    const template = makeTemplate("t1", {
      well: "WELL",
      plate_name: "PLATE",
      concentration: "CONC",
      batch_ref: "BATCH",
      compound_ref: "CPD",
      readout_headers: ["INHIB"],
    });
    const headers = ["WELL", "PLATE", "CONC", "BATCH", "CPD", "INHIB", "EXTRA"];
    const result = applyTemplateToDraft(draft, template, headers);
    expect(result.roles.WELL).toBe("well");
    expect(result.roles.PLATE).toBe("plate_name");
    expect(result.roles.CONC).toBe("concentration");
    expect(result.roles.BATCH).toBe("batch_ref");
    expect(result.roles.CPD).toBe("compound_ref");
    expect(result.roles.INHIB).toBe("readout");
    // Headers not in the template mapping are untouched (still undefined)
    expect(result.roles.EXTRA).toBeUndefined();
  });

  it("skips headers from the template that are absent in the file", () => {
    const draft = emptyDraft();
    const template = makeTemplate("t2", {
      well: "WELL",
      batch_ref: "MISSING_BATCH",
    });
    const headers = ["WELL", "INHIB"];
    const result = applyTemplateToDraft(draft, template, headers);
    expect(result.roles.WELL).toBe("well");
    expect(result.roles.MISSING_BATCH).toBeUndefined();
  });

  it("does not mutate the original draft", () => {
    const draft = emptyDraft();
    const template = makeTemplate("t3", { well: "WELL" });
    applyTemplateToDraft(draft, template, ["WELL"]);
    expect(draft.roles).toEqual({});
  });
});

// ─── suggestionToInitialDraft ─────────────────────────────────────────────────

describe("suggestionToInitialDraft", () => {
  it("maps each suggestion's header → role", () => {
    const suggestions = [
      {
        header: "WELL",
        role: "well" as const,
        confidence: "high" as const,
        reason: "exact match",
        readout_definition_id: null,
      },
      {
        header: "INHIB",
        role: "readout" as const,
        confidence: "medium" as const,
        reason: "name match",
        readout_definition_id: "rd-1",
      },
    ];
    const draft = suggestionToInitialDraft(suggestions);
    expect(draft.roles.WELL).toBe("well");
    expect(draft.roles.INHIB).toBe("readout");
    expect(draft.readoutDefByHeader.INHIB).toBe("rd-1");
  });

  it("does not set readoutDefByHeader when readout_definition_id is null", () => {
    const suggestions = [
      {
        header: "INHIB2",
        role: "readout" as const,
        confidence: "low" as const,
        reason: "fuzzy",
        readout_definition_id: null,
      },
    ];
    const draft = suggestionToInitialDraft(suggestions);
    expect(draft.readoutDefByHeader.INHIB2).toBeUndefined();
  });
});

// ─── pickBestTemplate ─────────────────────────────────────────────────────────

describe("pickBestTemplate", () => {
  it("returns the highest-scored template when score >= 0.7", () => {
    const headers = ["WELL", "PLATE", "CONC", "INHIB", "EXTRA"];
    const poor = makeTemplate("poor", {
      well: "WELL",
      plate_name: "OTHER_PLATE",
      concentration: "OTHER_CONC",
      readout_headers: ["OTHER_INHIB"],
    });
    const good = makeTemplate("good", {
      well: "WELL",
      plate_name: "PLATE",
      concentration: "CONC",
      readout_headers: ["INHIB"],
    });
    const result = pickBestTemplate([poor, good], headers);
    expect(result?.id).toBe("good");
  });

  it("returns null when the best score is below 0.7", () => {
    const headers = ["WELL", "COL_A", "COL_B"];
    // template only matches WELL → score = 1/4 = 0.25
    const t = makeTemplate("weak", {
      well: "WELL",
      plate_name: "MISSING_PLATE",
      concentration: "MISSING_CONC",
      readout_headers: ["MISSING_INHIB"],
    });
    expect(pickBestTemplate([t], headers)).toBeNull();
  });

  it("returns null for an empty templates array", () => {
    expect(pickBestTemplate([], ["WELL", "INHIB"])).toBeNull();
  });

  it("requires the well column to be present for any positive score", () => {
    // Template with well=MISSING means scoreTemplate returns 0 immediately.
    const headers = ["PLATE", "CONC", "INHIB"];
    const t = makeTemplate("no-well", {
      well: "MISSING",
      plate_name: "PLATE",
      concentration: "CONC",
      readout_headers: ["INHIB"],
    });
    expect(pickBestTemplate([t], headers)).toBeNull();
  });
});
