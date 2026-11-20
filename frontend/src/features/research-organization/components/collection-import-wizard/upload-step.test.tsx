import { buildCollectionImportTemplate } from "@/features/research-organization/lib/parse-collection-import-csv";
import { saveText } from "@/shared/lib/api/download";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UploadStep } from "./upload-step";

vi.mock("@/shared/lib/api/download", () => ({ saveText: vi.fn() }));

describe("UploadStep", () => {
  it("invokes onParsed when a valid CSV is uploaded", async () => {
    const onParsed = vi.fn();
    render(<UploadStep onParsed={onParsed} />);
    const file = new File(["registration_number,name\nCC-000001,Phenol\n"], "import.csv", {
      type: "text/csv",
    });
    const input = screen.getByLabelText(/upload csv/i) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await new Promise((r) => setTimeout(r, 100));
    expect(onParsed).toHaveBeenCalled();
  });

  it("downloads the import template", () => {
    render(<UploadStep onParsed={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /download template/i }));
    expect(saveText).toHaveBeenCalledExactlyOnceWith(
      buildCollectionImportTemplate(),
      "collection-import-template.csv",
    );
  });
});
