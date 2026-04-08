"use client";

import { useState } from "react";
import { Archive, Pencil } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { DetailShell } from "@/shared/components/detail-shell";
import { MemberName } from "@/shared/components/entity-name";
import { useProject, useArchiveProject } from "../hooks/use-projects";
import { CreateProjectDialog } from "./create-project-dialog";
import { CollectionList } from "./collection-list";
import { SavedSearchList } from "./saved-search-list";
import { ProjectMembers } from "./project-members";

interface ProjectDetailProps {
  projectId: string;
}

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const query = useProject(projectId);
  const archiveMutation = useArchiveProject();

  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  return (
    <>
      <DetailShell
        query={query}
        backHref="/projects"
        backLabel="Back to Projects"
        title={(p) => p.name}
        badge={(p) => ({ status: p.status })}
        notFoundMessage="Project not found."
        actions={(p) =>
          p.status !== "archived" ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditOpen(true)}
              >
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setArchiveOpen(true)}
              >
                <Archive className="mr-2 h-4 w-4" />
                Archive
              </Button>
            </>
          ) : undefined
        }
      >
        {(project) => (
          <>
            {/* Metadata Card */}
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
                  <div>
                    <p className="text-sm text-muted-foreground">Description</p>
                    <p className="font-medium">
                      {project.description || "\u2014"}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                    <p className="font-medium capitalize">{project.status}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Created By</p>
                    <p className="text-sm font-medium">
                      <MemberName id={project.created_by} />
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Collections */}
            <Card>
              <CardHeader>
                <CardTitle>Collections</CardTitle>
              </CardHeader>
              <CardContent>
                <CollectionList projectId={projectId} />
              </CardContent>
            </Card>

            {/* Saved Searches */}
            <Card>
              <CardHeader>
                <CardTitle>Saved Searches</CardTitle>
              </CardHeader>
              <CardContent>
                <SavedSearchList projectId={projectId} />
              </CardContent>
            </Card>

            {/* Members */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Members</CardTitle>
              </CardHeader>
              <CardContent>
                <ProjectMembers projectId={projectId} />
              </CardContent>
            </Card>
          </>
        )}
      </DetailShell>

      {/* Edit dialog */}
      <CreateProjectDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        project={query.data}
      />

      {/* Archive confirmation */}
      <AlertDialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive project?</AlertDialogTitle>
            <AlertDialogDescription>
              Archiving &ldquo;{query.data?.name}&rdquo; will hide it from the
              active projects list. Collections and saved searches will be
              preserved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (query.data) {
                  archiveMutation.mutate(query.data.id, {
                    onSuccess: () => setArchiveOpen(false),
                  });
                }
              }}
              disabled={archiveMutation.isPending}
            >
              {archiveMutation.isPending ? "Archiving..." : "Archive"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
