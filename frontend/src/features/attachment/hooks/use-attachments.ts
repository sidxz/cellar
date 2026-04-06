"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  customInstance,
  getApiBaseUrl,
} from "@/shared/lib/api/custom-instance";
import { getSentinelClient } from "@/shared/lib/auth/config";
import { showError, showSuccess } from "@/shared/lib/toast";
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
      showError(err.message);
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
      showError(err.message);
    },
  });
}

export function useDownloadAttachment() {
  return async (attachmentId: string, fileName: string) => {
    const client =
      typeof window !== "undefined" ? getSentinelClient() : null;
    const authHeaders = client?.isAuthenticated ? client.getHeaders() : {};
    const response = await fetch(
      `${getApiBaseUrl()}/api/v1/attachments/${attachmentId}/download`,
      { headers: { ...authHeaders } }
    );
    if (!response.ok) {
      throw new Error(`Download failed: ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  };
}
