"use client";

import { AddToProjectDialog } from "@/features/research-organization/components/add-to-project-dialog";
import { useMoleculeProjects } from "@/features/research-organization/hooks/use-molecule-projects";
import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { Badge } from "@/shared/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";

interface ProjectsTabProps {
  moleculeId: string;
}

export function ProjectsTab({ moleculeId }: ProjectsTabProps) {
  const { data: projectIds } = useMoleculeProjects(moleculeId);
  const { data: allProjects } = useProjects();
  const projectNames = allProjects?.filter((p) => projectIds?.includes(p.id));

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Projects</CardTitle>
        <AddToProjectDialog moleculeId={moleculeId} existingProjectIds={projectIds ?? []} />
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {projectNames?.map((p) => (
            <Badge key={p.id} variant="secondary">
              {p.name}
            </Badge>
          ))}
          {(!projectNames || projectNames.length === 0) && (
            <span className="text-muted-foreground text-sm">Not in any project</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
