import { describe, expect, it } from "vitest";

import { SDF_TITLE_HEADER, readFileColumns, readSdfColumns } from "./read-file-columns";

describe("readFileColumns (CSV)", () => {
  it("lists the headers and the first 3 distinct non-empty values of each", async () => {
    const csv = [
      "Molecule Name,SMILES,Batch Name,scientist",
      "SACC-1,CCO,001,",
      "SACC-1,CCO,002,",
      "SACC-2,,001,",
      "SACC-3,CCN,003,",
      "SACC-4,CCC,004,",
    ].join("\n");
    const cols = await readFileColumns(new File([csv], "export.csv"), "csv");
    expect(cols.headers).toEqual(["Molecule Name", "SMILES", "Batch Name", "scientist"]);
    expect(cols.samples).toEqual({
      "Molecule Name": ["SACC-1", "SACC-2", "SACC-3"],
      SMILES: ["CCO", "CCN", "CCC"],
      "Batch Name": ["001", "002", "003"],
      scientist: [],
    });
  });
});

const record = (title: string, props: string) =>
  `${title}\n  RDKit          2D\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n${props}\n$$$$\n`;

describe("readSdfColumns", () => {
  it("puts the title line first and lists every > <Name> property, keeping multi-line values", () => {
    const sdf =
      record("SACC-0519397", "> <Synonyms>\nJSF-1187\n\n>  <LGCY Batch Name>  (1)\nMSD-1\n") +
      record(
        "SACC-0428730",
        "> <Synonyms>\nJSF-2001\nTAMU-1585\n\n> <Batch Molecule-Batch ID>\nSACC-0428730-002\n",
      );
    const cols = readSdfColumns(sdf);
    expect(cols.headers).toEqual([
      SDF_TITLE_HEADER,
      "Synonyms",
      "LGCY Batch Name",
      "Batch Molecule-Batch ID",
    ]);
    expect(cols.samples[SDF_TITLE_HEADER]).toEqual(["SACC-0519397", "SACC-0428730"]);
    expect(cols.samples.Synonyms).toEqual(["JSF-1187", "JSF-2001\nTAMU-1585"]);
    expect(cols.samples["LGCY Batch Name"]).toEqual(["MSD-1"]);
    expect(cols.samples["Batch Molecule-Batch ID"]).toEqual(["SACC-0428730-002"]);
  });

  it("reads an SDF File through readFileColumns", async () => {
    const sdf = record("Aspirin", "> <CAS>\n50-78-2\n");
    // jsdom's File has no text() (browsers do), and Node's Response reads a jsdom
    // File as "[object File]", so give the test File the browser method.
    const file = Object.assign(new File([sdf], "set.sdf"), { text: async () => sdf });
    const cols = await readFileColumns(file, "sdf");
    expect(cols.headers).toEqual([SDF_TITLE_HEADER, "CAS"]);
    expect(cols.samples.CAS).toEqual(["50-78-2"]);
  });
});
