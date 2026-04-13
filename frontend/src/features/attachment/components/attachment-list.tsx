"use client";

import { useState } from "react";
import {
  Download,
  File as FileIcon,
  FileSpreadsheet,
  FileText,
  Image,
  Trash2,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import {
  useAttachments,
  useDeleteAttachment,
  useDownloadAttachment,
} from "../hooks/use-attachments";
import type { AttachableType, AttachmentResponse } from "../types";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

function getMimeIcon(mimeType: string) {
  if (mimeType.startsWith("image/")) return Image;
  if (
    mimeType.includes("spreadsheet") ||
    mimeType.includes("csv") ||
    mimeType.includes("excel")
  )
    return FileSpreadsheet;
  if (mimeType === "application/pdf" || mimeType.startsWith("text/"))
    return FileText;
  return FileIcon;
}

interface AttachmentListProps {
  entityType: AttachableType;
  entityId: string;
}

export function AttachmentList({ entityType, entityId }: AttachmentListProps) {
  const { data: attachments, isLoading } = useAttachments(entityType, entityId);
  const deleteMutation = useDeleteAttachment(entityType, entityId);
  const downloadFn = useDownloadAttachment();
  const [deleteTarget, setDeleteTarget] = useState<AttachmentResponse | null>(
    null
  );

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading files...</p>;
  }

  if (!attachments?.length) {
    return (
      <p className="text-sm text-muted-foreground">No files attached yet.</p>
    );
  }

  return (
    <>
      <div className="divide-y rounded-lg border">
        {attachments.map((att) => {
          const Icon = getMimeIcon(att.mime_type);
          return (
            <div
              key={att.id}
              className="flex items-center justify-between px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <Icon className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{att.file_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(att.file_size)} &middot;{" "}
                    {new Date(att.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => downloadFn(att.id, att.file_name)}
                >
                  <Download className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setDeleteTarget(att)}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete file?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete{" "}
              <strong>{deleteTarget?.file_name}</strong>. This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget.id);
                  setDeleteTarget(null);
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
