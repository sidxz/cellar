import type { AttachmentResponse as GeneratedAttachmentResponse } from "@/shared/lib/api/model";

// Backend-owned shape: alias the orval-generated type so it stays in sync.
export type AttachmentResponse = GeneratedAttachmentResponse;

// Client-only union (no backend counterpart): the set of entities an
// attachment can be associated with, used to scope upload/list routes.
export type AttachableType =
  | "molecule"
  | "batch"
  | "sample"
  | "plate"
  | "shipment"
  | "protocol"
  | "run";
