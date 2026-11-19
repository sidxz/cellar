import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Protocol } from "../../types";
import { useReadoutDefinitionForm } from "./use-readout-definition-form";

const protocol = {
  readout_definitions: [
    { name: "Signal", data_type: "numeric", normalizations: ["percent_inhibition"] },
  ],
} as unknown as Protocol;

describe("useReadoutDefinitionForm — Y readout pick", () => {
  it("leaves Top, Bottom and Hill free when a % Y readout is picked", () => {
    const { result } = renderHook(() => useReadoutDefinitionForm());

    act(() => result.current.handleDrYReadoutChange("Signal"));

    expect(result.current.drYReadout).toBe("Signal");
    expect(result.current.drTopMode).toBe("free");
    expect(result.current.drBottomMode).toBe("free");
    expect(result.current.drHillCustomRange).toBe(false);
  });

  it("still applies the suggested ranges when the scientist asks for them", () => {
    const { result } = renderHook(() => useReadoutDefinitionForm());

    act(() => result.current.handleDrYReadoutChange("Signal"));
    act(() => result.current.applySuggestedRanges(protocol));

    expect(result.current.drTopMode).toBe("range");
    expect(result.current.drBottomMode).toBe("range");
    expect(result.current.drHillCustomRange).toBe(true);
  });
});
