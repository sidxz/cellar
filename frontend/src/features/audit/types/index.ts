// ─── API DTOs (orval-generated; aliased per project rule) ────────────────────
//
// These are the project-mandated source of truth, regenerated from the live
// backend OpenAPI. We alias the generated types to domain-friendly names so
// call sites don't churn. Never hand-roll a mirror of a backend DTO.
//
// The orval nullable-wrapper inner types (AuditOperationResponseReason, etc.)
// all resolve to `string | null` / `ElectronicSignatureResponse | null`, so the
// aliases below are field-for-field equivalent to the previous hand types.

import type {
  AuditEntryResponse,
  AuditOperationResponse,
  ElectronicSignatureResponse,
} from "@/shared/lib/api/model";

export type AuditEntry = AuditEntryResponse;
export type ElectronicSignature = ElectronicSignatureResponse;
export type AuditOperation = AuditOperationResponse;
