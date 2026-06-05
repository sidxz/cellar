"use client";

import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { Button } from "@/shared/components/ui/button";
import { formatDate } from "@/shared/lib/format-date";
import { formatFileSize } from "@/shared/lib/format-number";
import { Download, File as FileIcon, FileSpreadsheet, FileText, Image, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  useAttachments,
  useDeleteAttachment,
  useDownloadAttachment,
} from "../hooks/use-attachments";
import type { AttachableType, AttachmentResponse } from "../types";

function getMimeIcon(mimeType: string) {
  if (mimeType.startsWith("image/")) return Image;
  if (mimeType.includes("spreadsheet") || mimeType.includes("csv") || mimeType.includes("excel"))
    return FileSpreadsheet;
  if (mimeType === "application/pdf" || mimeType.startsWith("text/")) return FileText;
  return FileIcon;
}

interface AttachmentListProps {
  entityType: AttachableType;
  entityId: string;
}

export function AttachmentList({ entityType, entityId }: AttachmentListProps) {
  const { data: attachments, isLoading } = useAttachments(entityType, entityId);
  const deleteMutation = useDeleteAttachment(entityType, entityId);
  const downloadMutation = useDownloadAttachment();
  const [deleteTarget, setDeleteTarget] = useState<AttachmentResponse | null>(null);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading files...</p>;
  }

  if (!attachments?.length) {
    return <p className="text-sm text-muted-foreground">No files attached yet.</p>;
  }

  return (
    <>
      <div className="divide-y rounded-lg border">
        {attachments.map((att) => {
          const Icon = getMimeIcon(att.mime_type);
          return (
            <div key={att.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <Icon className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{att.file_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(att.file_size)} &middot; {formatDate(att.created_at)}
                  </p>
                </div>
              </div>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Download ${att.file_name}`}
                  onClick={() =>
                    downloadMutation.mutate({
                      attachmentId: att.id,
                      fileName: att.file_name,
                    })
                  }
                  disabled={downloadMutation.isPending}
                >
                  <Download className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(att)}>
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete file?"
        description={`This will permanently delete "${deleteTarget?.file_name ?? ""}". This action cannot be undone.`}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
            setDeleteTarget(null);
          }
        }}
        isPending={deleteMutation.isPending}
      />
    </>
  );
}
