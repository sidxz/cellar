// ─── Interfaces ───────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: string;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  entry_type: string;
}

export interface ElectronicSignature {
  signer_id: string;
  reason: string;
  signed_at: string;
}

export interface AuditOperation {
  id: string;
  workspace_id: string;
  entity_type: string;
  entity_id: string;
  operation_type: string;
  performed_by: string;
  performed_at: string;
  reason: string | null;
  entries: AuditEntry[];
  signature: ElectronicSignature | null;
}
