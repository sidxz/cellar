import { describe, expect, it } from "vitest";
import { formatKeywordValues, parseKeywordValues } from "./keyword-values";

describe("pasted keyword values", () => {
  it("accepts mixed CSV and spreadsheet separators and ignores blank or repeated values", () => {
    expect(parseKeywordValues(" UCP1172, SDDC-1230\r\nTAMU-1585\tJSF-1187;UCP1172, ,\n")).toEqual([
      "UCP1172",
      "SDDC-1230",
      "TAMU-1585",
      "JSF-1187",
    ]);
  });

  it("keeps quoted commas and escaped quotes in chemical names", () => {
    expect(parseKeywordValues('"1,2-dichlorobenzene","compound ""A""",aspirin')).toEqual([
      "1,2-dichlorobenzene",
      'compound "A"',
      "aspirin",
    ]);
  });

  it("keeps locant commas inside a typed chemical name but splits an ID list", () => {
    expect(
      parseKeywordValues(
        "2,4-dinitrophenol, N,N-dimethylformamide\n1,1'-biphenyl\n(2S,3R)-threonine,2,4,6-trinitrotoluene",
      ),
    ).toEqual([
      "2,4-dinitrophenol",
      "N,N-dimethylformamide",
      "1,1'-biphenyl",
      "(2S,3R)-threonine",
      "2,4,6-trinitrotoluene",
    ]);
    expect(parseKeywordValues("CMPD-1,CMPD-2,UCP1172,2-SDDC")).toEqual([
      "CMPD-1",
      "CMPD-2",
      "UCP1172",
      "2-SDDC",
    ]);
    expect(parseKeywordValues("1,2,3")).toEqual(["1", "2", "3"]);
  });

  it("shows saved names bare and quotes only values that would otherwise split", () => {
    expect(formatKeywordValues(["2,4-dinitrophenol", "vendor;123", "A,B"])).toBe(
      '2,4-dinitrophenol\n"vendor;123"\n"A,B"',
    );
  });

  it("round-trips saved values without splitting punctuation in them", () => {
    const values = ["1,2-dichlorobenzene", "vendor;123", 'compound "A"'];
    expect(parseKeywordValues(formatKeywordValues(values))).toEqual(values);
    expect(parseKeywordValues(" ,;\t\n ")).toEqual([]);
  });
});
