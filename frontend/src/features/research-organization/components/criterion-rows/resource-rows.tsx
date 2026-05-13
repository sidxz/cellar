"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Trash2 } from "lucide-react";
import { useCollections } from "../../hooks/use-collections";
import { useProjects } from "../../hooks/use-projects";
import type { CollectionCriterion, ProjectCriterion } from "../../types";

export function CollectionCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: CollectionCriterion;
  onChange: (c: CollectionCriterion) => void;
  onRemove: () => void;
}) {
  const { data: collections } = useCollections();

  return (
    <div className="flex items-end gap-2">
      <div className="w-64">
        <Label className="text-xs text-muted-foreground">In Collection</Label>
        <Select
          value={criterion.collection_id || undefined}
          onValueChange={(v) => onChange({ ...criterion, collection_id: v })}
        >
          <SelectTrigger className="h-9">
            <SelectValue placeholder="Select collection..." />
          </SelectTrigger>
          <SelectContent>
            {collections?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name} ({c.molecule_count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}

export function ProjectCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ProjectCriterion;
  onChange: (c: ProjectCriterion) => void;
  onRemove: () => void;
}) {
  const { data: projects } = useProjects();

  return (
    <div className="flex items-start gap-2 flex-wrap">
      <div className="flex items-end gap-2 flex-1 flex-wrap">
        <div className="w-56">
          <Label className="text-xs text-muted-foreground">Add Project</Label>
          <Select
            value=""
            onValueChange={(val) => {
              const current = criterion.project_ids ?? [];
              const updated = current.includes(val)
                ? current.filter((id) => id !== val)
                : [...current, val];
              onChange({ ...criterion, project_ids: updated });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Add project..." />
            </SelectTrigger>
            <SelectContent>
              {projects
                ?.filter((p) => p.status === "active")
                .map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap gap-1 items-center min-h-9">
          {(criterion.project_ids ?? []).map((id) => {
            const proj = projects?.find((p) => p.id === id);
            return proj ? (
              <Badge key={id} variant="secondary" className="text-xs">
                {proj.name}
              </Badge>
            ) : null;
          })}
        </div>
      </div>
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0 self-end" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}
