"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreateVocabularyInput,
  UpdateVocabularyInput,
  Vocabulary,
} from "../types";

const VOCAB_KEY = ["vocabularies"];

export function useVocabularies() {
  return useQuery({
    queryKey: VOCAB_KEY,
    queryFn: () =>
      customInstance<Vocabulary[]>({
        url: "/api/v1/vocabularies",
        method: "GET",
      }),
  });
}

export function useCreateVocabulary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateVocabularyInput) =>
      customInstance<Vocabulary>({
        url: "/api/v1/vocabularies",
        method: "POST",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}

export function useUpdateVocabulary(vocabId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateVocabularyInput) =>
      customInstance<Vocabulary>({
        url: `/api/v1/vocabularies/${vocabId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}

export function useDeleteVocabulary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vocabId: string) =>
      customInstance<void>({
        url: `/api/v1/vocabularies/${vocabId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: VOCAB_KEY }),
  });
}
