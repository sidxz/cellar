"use client";

import { Upload } from "lucide-react";
import { useCallback, useEffect } from "react";
import { useDropzone } from "react-dropzone";

import { cn } from "@/shared/lib/utils";

/**
 * Single-file CSV/XLSX dropzone for the screening-assay import wizards.
 *
 * Wraps react-dropzone so drag-active styling, keyboard accessibility, and the
 * hidden file input come for free (no hand-rolled isDragging/onDragOver state).
 * The chosen file is reported through `onFile`; the parent owns the file state
 * and the parsing mutation, so this component stays presentation-only.
 *
 * `onOpenReady` hands the parent react-dropzone's `open()` so a sibling button
 * (e.g. a dialog footer "Choose file") can trigger the native file picker.
 */
interface CsvDropzoneProps {
  /** The currently selected file, shown by name once chosen. */
  file: File | null;
  /** Called with the picked file on drop or browse. */
  onFile: (file: File) => void;
  /** When true, shows a "Parsing…" affordance and disables interaction. */
  isPending?: boolean;
  /** Receives react-dropzone's `open()` so external buttons can launch the picker. */
  onOpenReady?: (open: () => void) => void;
}

export function CsvDropzone({ file, onFile, isPending = false, onOpenReady }: CsvDropzoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      const f = accepted[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    maxFiles: 1,
    multiple: false,
    disabled: isPending,
  });

  useEffect(() => {
    onOpenReady?.(open);
  }, [open, onOpenReady]);

  return (
    <div className="py-2">
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-muted-foreground/50",
        )}
      >
        <input {...getInputProps()} />
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          {isPending
            ? "Parsing…"
            : file
              ? file.name
              : "Drop a CSV or XLSX here, or click to browse"}
        </p>
      </div>
    </div>
  );
}
