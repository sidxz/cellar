"use client";

import { FileUploadZone, AttachmentList } from "@/features/attachment";

interface FilesTabProps {
  protocolId: string;
}

export function FilesTab({ protocolId }: FilesTabProps) {
  return (
    <div className="space-y-6">
      <FileUploadZone entityType="protocol" entityId={protocolId} />
      <AttachmentList entityType="protocol" entityId={protocolId} />
    </div>
  );
}
