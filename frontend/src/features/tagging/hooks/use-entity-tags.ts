"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { EntityTag, Tag, TagInput, TaggableEntity } from "../types";

const entityTagsKey = (entity: TaggableEntity, id: string) => ["entity-tags", entity, id];

export function useEntityTags(entity: TaggableEntity, id: string | undefined) {
  return useQuery({
    queryKey: id ? entityTagsKey(entity, id) : ["entity-tags", entity, "none"],
    enabled: !!id,
    queryFn: () =>
      customInstance<EntityTag[]>({ url: `${API_V1}/${entity}/${id}/tags`, method: "GET" }),
  });
}

export function useAssignTag(entity: TaggableEntity, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TagInput) =>
      customInstance<Tag>({
        url: `${API_V1}/${entity}/${id}/tags`,
        method: "POST",
        data: { key: input.key, value: input.value ?? null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: entityTagsKey(entity, id) });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
    onError: (e: Error) => showError(e.message || "Failed to add tag"),
  });
}

export function useUnassignTag(entity: TaggableEntity, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tagId: string) =>
      customInstance<void>({
        url: `${API_V1}/${entity}/${id}/tags/${tagId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityTagsKey(entity, id) }),
    onError: (e: Error) => showError(e.message || "Failed to remove tag"),
  });
}
