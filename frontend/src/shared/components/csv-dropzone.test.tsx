import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CsvDropzone } from "./csv-dropzone";

describe("CsvDropzone", () => {
  it("shows the browse prompt when no file is selected", () => {
    render(<CsvDropzone file={null} onFile={vi.fn()} />);
    expect(screen.getByText(/drop a csv or xlsx here, or click to browse/i)).toBeInTheDocument();
  });

  it("shows the file name once a file is selected", () => {
    const file = new File(["a,b"], "results.csv", { type: "text/csv" });
    render(<CsvDropzone file={file} onFile={vi.fn()} />);
    expect(screen.getByText("results.csv")).toBeInTheDocument();
  });

  it("shows a parsing affordance while pending", () => {
    render(<CsvDropzone file={null} onFile={vi.fn()} isPending />);
    expect(screen.getByText(/parsing/i)).toBeInTheDocument();
  });

  it("restricts the file input to CSV and XLSX", () => {
    render(<CsvDropzone file={null} onFile={vi.fn()} />);
    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    expect(input.accept).toContain(".csv");
    expect(input.accept).toContain(".xlsx");
  });

  it("hands react-dropzone's open() to onOpenReady so an external button can launch the picker", () => {
    const onOpenReady = vi.fn();
    render(<CsvDropzone file={null} onFile={vi.fn()} onOpenReady={onOpenReady} />);
    expect(onOpenReady).toHaveBeenCalledWith(expect.any(Function));
  });

  it("widens the accepted extensions when given a custom accept map", () => {
    render(
      <CsvDropzone
        file={null}
        onFile={vi.fn()}
        accept={{
          "text/csv": [".csv"],
          "chemical/x-mdl-sdfile": [".sdf", ".sd"],
        }}
      />,
    );
    const input = document.querySelector("input[type='file']") as HTMLInputElement;
    expect(input.accept).toContain(".csv");
    expect(input.accept).toContain(".sdf");
    expect(input.accept).toContain(".sd");
  });

  it("renders the custom prompt and format hint when no file is selected", () => {
    render(
      <CsvDropzone
        file={null}
        onFile={vi.fn()}
        prompt="Drop a file here or click to browse"
        hint="CSV, TSV, TXT, XLSX"
      />,
    );
    expect(screen.getByText("Drop a file here or click to browse")).toBeInTheDocument();
    expect(screen.getByText("CSV, TSV, TXT, XLSX")).toBeInTheDocument();
  });

  it("hides the format hint once a file is selected", () => {
    const file = new File(["a,b"], "results.csv", { type: "text/csv" });
    render(<CsvDropzone file={file} onFile={vi.fn()} hint="CSV, TSV, TXT, XLSX" />);
    expect(screen.queryByText("CSV, TSV, TXT, XLSX")).not.toBeInTheDocument();
    expect(screen.getByText("results.csv")).toBeInTheDocument();
  });
});
