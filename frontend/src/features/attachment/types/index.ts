export interface AttachmentResponse {
  id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  attachable_type: string;
  attachable_id: string;
  uploaded_by: string;
  created_at: string;
}

export type AttachableType = "molecule" | "batch" | "sample" | "plate" | "shipment" | "protocol" | "run";
