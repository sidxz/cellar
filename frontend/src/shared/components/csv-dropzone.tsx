"use client";

import { FileText, Upload, X } from "lucide-react";
import { useCallback, useEffect } from "react";
import { type Accept, useDropzone } from "react-dropzone";

import { Button } from "@/shared/components/ui/button";
import { formatFileSize } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";

/**
 * Default accept map: CSV + XLSX. Callers that take a wider set (e.g. TSV/TXT
 * for plate-reader exports, or SDF for chemical-registration bulk upload) pass
 * their own `accept` map — the only axis on which the real call sites diverge.
 */
const CSV_XLSX_ACCEPT: Accept = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

/**
 * Single-file dropzone for the import wizards (screening-assay run/summary,
 * inventory plate import, chemical-registration bulk upload).
 *
 * Wraps react-dropzone so drag-active styling, keyboard accessibility, and the
 * hidden file input come for free (no hand-rolled isDragging/onDragOver state).
 * The chosen file is reported through `onFile`; the parent owns the file state
 * and the parsing mutation, so this component stays presentation-only.
 *
 * `onOpenReady` hands the parent react-dropzone's `open()` so a sibling button
 * (e.g. a dialog footer "Choose file") can trigger the native file picker.
 *
 * `accept`/`prompt`/`hint` let a caller widen the accepted extensions and tune
 * the copy without forking the markup; they default to the CSV/XLSX variant.
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
  /** react-dropzone accept map; defaults to CSV + XLSX. */
  accept?: Accept;
  /** Primary prompt shown when no file is selected. */
  prompt?: string;
  /** Optional secondary line listing accepted formats. */
  hint?: string;
  /** Replace the selected dropzone with one file card and explicit actions. */
  compactSelected?: boolean;
  onRemove?: () => void;
  onRejected?: (message: string) => void;
}

export function CsvDropzone({
  file,
  onFile,
  isPending = false,
  onOpenReady,
  accept = CSV_XLSX_ACCEPT,
  prompt = "Drop a CSV or XLSX here, or click to browse",
  hint,
  compactSelected = false,
  onRemove,
  onRejected,
}: CsvDropzoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      const f = accepted[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept,
    maxFiles: 1,
    multiple: false,
    disabled: isPending,
    onDropRejected: (rejected) => {
      const formats = Object.values(accept).flat().join(", ");
      onRejected?.(
        rejected.some((file) => file.errors.some((error) => error.code === "too-many-files"))
          ? "Choose one file at a time."
          : `This file type is not supported. Choose ${formats}.`,
      );
    },
  });

  useEffect(() => {
    onOpenReady?.(open);
  }, [open, onOpenReady]);

  if (compactSelected && file) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/25 bg-primary/5 p-4">
        <input {...getInputProps()} />
        <FileText className="size-6 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="break-all text-sm font-medium">{file.name}</p>
          <p className="mt-1 text-sm text-foreground/70">
            {formatFileSize(file.size)} · {file.name.split(".").pop()?.toUpperCase()}
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={open} disabled={isPending}>
          Replace file
        </Button>
        {onRemove && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onRemove}
            disabled={isPending}
            aria-label="Remove file"
          >
            <X className="size-4" />
          </Button>
        )}
      </div>
    );
  }

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
          {isPending ? "Parsing…" : file ? file.name : prompt}
        </p>
        {!isPending && !file && hint && (
          <p className="mt-1 text-xs text-muted-foreground/60">{hint}</p>
        )}
      </div>
    </div>
  );
}
