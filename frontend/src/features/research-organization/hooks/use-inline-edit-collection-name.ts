"use client";

import { useCallback, useEffect, useState } from "react";
import { useUpdateCollection } from "./use-collections";

export interface UseInlineEditCollectionName {
  isEditing: boolean;
  draft: string;
  isPending: boolean;
  startEdit: () => void;
  cancel: () => void;
  commit: () => void;
  setDraft: (next: string) => void;
}

export function useInlineEditCollectionName(
  collectionId: string,
  currentName: string,
): UseInlineEditCollectionName {
  const update = useUpdateCollection(collectionId);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(currentName);

  useEffect(() => {
    if (!isEditing) setDraft(currentName);
  }, [currentName, isEditing]);

  const startEdit = useCallback(() => {
    setDraft(currentName);
    setIsEditing(true);
  }, [currentName]);

  const cancel = useCallback(() => {
    setDraft(currentName);
    setIsEditing(false);
  }, [currentName]);

  const commit = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === currentName) {
      setIsEditing(false);
      setDraft(currentName);
      return;
    }
    update.mutate({ name: trimmed });
    setIsEditing(false);
  }, [draft, currentName, update]);

  return {
    isEditing,
    draft,
    isPending: update.isPending,
    startEdit,
    cancel,
    commit,
    setDraft,
  };
}
