export type ExportFormat = "csv" | "sdf" | "xlsx" | "pdf";
export type ExportSource = "search";
export type ExportStatus =
  | "pending"
  | "running"
  | "ready"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "expired";

export interface ExportRequest {
  source: ExportSource;
  format: ExportFormat;
  filename_hint?: string;
  payload: Record<string, unknown>;
}

export interface ExportJob {
  id: string;
  status: ExportStatus;
  format: ExportFormat;
  row_count: number | null;
  progress: number | null;
  error_message: string | null;
  download_url: string | null;
  byte_size: number | null;
  filename: string | null;
  requested_at: string;
  completed_at: string | null;
  expires_at: string | null;
}
