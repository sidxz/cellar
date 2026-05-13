"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { downloadFile } from "@/shared/lib/api/download";
import { showSuccess, showError } from "@/shared/lib/toast";
import type { AttachableType, AttachmentResponse } from "../types";

function attachmentsKey(entityType: AttachableType, entityId: string) {
  return ["attachments", entityType, entityId];
}

export function useAttachments(entityType: AttachableType, entityId: string) {
  return useQuery({
    queryKey: attachmentsKey(entityType, entityId),
    queryFn: () =>
      customInstance<AttachmentResponse[]>({
        url: `/api/v1/${entityType}/${entityId}/attachments`,
        method: "GET",
      }),
    enabled: !!entityId,
  });
}

export function useUploadAttachment(
  entityType: AttachableType,
  entityId: string
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<AttachmentResponse>({
        url: `/api/v1/${entityType}/${entityId}/attachments`,
        method: "POST",
        data: formData,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attachmentsKey(entityType, entityId) });
      showSuccess("File uploaded");
    },
    onError: (err: Error) => {
      showError(err.message || "File upload failed");
    },
  });
}

export function useDeleteAttachment(
  entityType: AttachableType,
  entityId: string
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      customInstance<void>({
        url: `/api/v1/attachments/${attachmentId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: attachmentsKey(entityType, entityId) });
      showSuccess("File deleted");
    },
    onError: (err: Error) => {
      showError(err.message || "File deletion failed");
    },
  });
}

export function useDownloadAttachment() {
  return useMutation({
    mutationFn: ({ attachmentId, fileName }: { attachmentId: string; fileName: string }) =>
      downloadFile({
        url: `/api/v1/attachments/${attachmentId}/download`,
        method: "GET",
        filename: fileName,
      }),
    onError: (err: Error) => {
      showError(err.message || "Download failed");
    },
  });
}
