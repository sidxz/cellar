"use client";

import { FileUploadZone, AttachmentList } from "@/features/attachment";

interface FilesTabProps {
  moleculeId: string;
}

export function FilesTab({ moleculeId }: FilesTabProps) {
  return (
    <div className="space-y-6">
      <FileUploadZone entityType="molecule" entityId={moleculeId} />
      <AttachmentList entityType="molecule" entityId={moleculeId} />
    </div>
  );
}
