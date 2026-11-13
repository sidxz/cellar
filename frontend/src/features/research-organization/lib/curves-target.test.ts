import type { Protocol } from "@/features/screening-assay/types";
import { describe, expect, it } from "vitest";
import { compoundRef, curvesTarget } from "./curves-target";

const protocol = { id: "p1", name: "Protocol 1" } as Protocol;
const A = { id: "m1", name: "ABC-0000001" };
const B = { id: "m2", name: "ABC-0000002" };

describe("curvesTarget", () => {
  it("is null without the flag, with a null flag, without a protocol and without compounds", () => {
    expect(curvesTarget({ ...protocol, has_measured_curves: false }, [A])).toBeNull();
    expect(curvesTarget({ ...protocol, has_measured_curves: null }, [A])).toBeNull();
    expect(curvesTarget(protocol, [A])).toBeNull();
    expect(curvesTarget(undefined, [A])).toBeNull();
    expect(curvesTarget({ ...protocol, has_measured_curves: true }, [])).toBeNull();
  });

  it("names the protocol and the compounds", () => {
    expect(curvesTarget({ ...protocol, has_measured_curves: true }, [A, B])).toEqual({
      protocol: { id: "p1", name: "Protocol 1" },
      molecules: [A, B],
    });
  });

  it("names a compound by its registration number, else its name", () => {
    expect(compoundRef({ id: "m1", registration_number: "ABC-0000001", name: "X" })).toEqual(A);
    expect(compoundRef({ id: "m1", registration_number: "", name: "X" })).toEqual({
      id: "m1",
      name: "X",
    });
  });
});
