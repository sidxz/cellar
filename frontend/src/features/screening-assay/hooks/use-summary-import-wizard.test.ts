import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ReadoutDefinitionResponse } from "@/shared/lib/api/model";

function makeReadoutDef(
  name: string,
  over: Partial<ReadoutDefinitionResponse> = {},
): ReadoutDefinitionResponse {
  return {
    id: `rd-${name}`,
    protocol_id: "proto-1",
    name,
    data_type: "numeric",
    is_calculated: false,
    display_order: 0,
    ...over,
  } as ReadoutDefinitionResponse;
}

const protocol = {
  readout_definitions: [
    makeReadoutDef("IC50"),
    makeReadoutDef("Percent Inhibition", { is_calculated: true }),
  ],
};

vi.mock("./use-protocols", () => ({
  useProtocol: () => ({ data: protocol }),
}));

const idleMutation = { mutate: vi.fn(), reset: vi.fn(), isPending: false };
vi.mock("./use-summary-import", () => ({
  usePreviewSummaryFile: () => idleMutation,
  useResolveSummaryFile: () => idleMutation,
  useImportSummaryFile: () => idleMutation,
}));

import { useSummaryImportWizard } from "./use-summary-import-wizard";

describe("useSummaryImportWizard", () => {
  it("omits calculated readouts from the column-target options", () => {
    const { result } = renderHook(() =>
      useSummaryImportWizard({
        runId: "run-1",
        protocolId: "proto-1",
        open: true,
        onOpenChange: vi.fn(),
      }),
    );

    expect(result.current.readoutDefOptions.map((o) => o.name)).toEqual(["IC50"]);
  });
});
