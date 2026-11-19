import { beforeEach, describe, expect, it } from "vitest";

import type { ColumnMappingBody } from "@/shared/lib/api/model";
import { useRegistrationWizard } from "./use-registration-wizard";

const file = new File(["name\n"], "a.csv");
const mapping: ColumnMappingBody = { columns: [{ header: "name", target: "name" }] };
const preview = { total_count: 0, error_count: 0, items: [] };

beforeEach(() => {
  useRegistrationWizard.getState().reset();
  const s = useRegistrationWizard.getState();
  useRegistrationWizard.setState({
    bulkInput: { ...s.bulkInput, file },
    bulkColumns: { headers: ["name"], samples: { name: [] } },
    bulkMapping: mapping,
    bulkPreview: preview,
  });
});

describe("registration wizard store (bulk mapping)", () => {
  it("starts the mapping and preview over when a different file is chosen", () => {
    useRegistrationWizard.getState().updateBulkInput({ file: new File(["smiles\n"], "b.csv") });
    const s = useRegistrationWizard.getState();
    expect(s.bulkColumns).toBeNull();
    expect(s.bulkMapping).toBeNull();
    expect(s.bulkPreview).toBeNull();
  });

  it("keeps the mapping when the same file or another field changes", () => {
    const { updateBulkInput } = useRegistrationWizard.getState();
    updateBulkInput({ file });
    updateBulkInput({ createBatchOnDuplicate: true });
    const s = useRegistrationWizard.getState();
    expect(s.bulkMapping).toBe(mapping);
    expect(s.bulkColumns).not.toBeNull();
    expect(s.bulkPreview).toBe(preview);
  });

  it("drops the preview when the mapping changes", () => {
    const next: ColumnMappingBody = { columns: [{ header: "name", target: "ignore" }] };
    useRegistrationWizard.getState().setBulkMapping(next);
    const s = useRegistrationWizard.getState();
    expect(s.bulkMapping).toBe(next);
    expect(s.bulkPreview).toBeNull();
  });
});
