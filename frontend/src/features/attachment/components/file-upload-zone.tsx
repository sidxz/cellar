"use client";

import { cn } from "@/shared/lib/utils";
import { Upload } from "lucide-react";
import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useUploadAttachment } from "../hooks/use-attachments";
import type { AttachableType } from "../types";

const BLOCKED_EXTENSIONS = new Set([
  ".exe",
  ".sh",
  ".bat",
  ".cmd",
  ".ps1",
  ".dll",
  ".so",
  ".com",
  ".msi",
  ".scr",
  ".zip",
  ".tar",
  ".gz",
  ".7z",
  ".rar",
  ".war",
  ".jar",
]);

/** Per-file upload cap. The byte limit and the UI copy both derive from this
 *  single value so they can't silently disagree. */
const MAX_FILE_MB = 100;
const MAX_SIZE = MAX_FILE_MB * 1024 * 1024;

interface FileUploadZoneProps {
  entityType: AttachableType;
  entityId: string;
}

export function FileUploadZone({ entityType, entityId }: FileUploadZoneProps) {
  const upload = useUploadAttachment(entityType, entityId);

  const onDrop = useCallback(
    (accepted: File[]) => {
      for (const file of accepted) {
        upload.mutate(file);
      }
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxSize: MAX_SIZE,
    validator: (file) => {
      const ext = file.name.includes(".") ? `.${file.name.split(".").pop()?.toLowerCase()}` : "";
      if (BLOCKED_EXTENSIONS.has(ext)) {
        return {
          code: "blocked-type",
          message: `${ext} files are not allowed`,
        };
      }
      return null;
    },
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors",
        isDragActive
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-muted-foreground/50",
      )}
    >
      <input {...getInputProps()} />
      <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
      {upload.isPending ? (
        <p className="text-sm text-muted-foreground">Uploading...</p>
      ) : isDragActive ? (
        <p className="text-sm text-muted-foreground">Drop files here</p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Drag &amp; drop files here, or click to browse
        </p>
      )}
      <p className="mt-1 text-xs text-muted-foreground/60">Max {MAX_FILE_MB} MB per file</p>
    </div>
  );
}
