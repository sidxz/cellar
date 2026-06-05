import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UploadStep } from "./upload-step";

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

  it("renders a Download Template button", () => {
    render(<UploadStep onParsed={vi.fn()} />);
    expect(screen.getByRole("button", { name: /download template/i })).toBeInTheDocument();
  });
});
