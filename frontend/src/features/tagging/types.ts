export type TaggableEntity = "molecules" | "protocols" | "projects" | "collections";

export interface Tag {
  id: string;
  workspace_id: string;
  key: string;
  value: string | null;
  created_by: string;
  created_at: string;
}

export interface TagInput {
  key: string;
  value?: string | null;
}
