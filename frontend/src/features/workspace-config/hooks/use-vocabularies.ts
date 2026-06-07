"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";
import type { CreateVocabularyInput, UpdateVocabularyInput, Vocabulary } from "../types";

const vocabHooks = createCrudHooks<Vocabulary, CreateVocabularyInput, UpdateVocabularyInput>({
  entityName: "Vocabulary",
  baseUrl: `${API_V1}/vocabularies`,
  queryKey: ["vocabularies"],
});

export const useVocabularies = vocabHooks.useList;
export const useCreateVocabulary = vocabHooks.useCreate;
export const useUpdateVocabulary = vocabHooks.useUpdate;
export const useDeleteVocabulary = vocabHooks.useDelete;

/** Fetch a single vocabulary by name and return its terms. */
export function useVocabularyTerms(name: string | null | undefined) {
  const { data: vocabularies } = useVocabularies();
  const vocab = vocabularies?.find((v) => v.name === name);
  return vocab?.terms ?? [];
}
