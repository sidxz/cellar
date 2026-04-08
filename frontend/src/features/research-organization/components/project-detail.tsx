"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Archive, Pencil, FolderKanban } from "lucide-react";
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
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { MemberName } from "@/shared/components/entity-name";
import { useProject, useArchiveProject } from "../hooks/use-projects";
import { CreateProjectDialog } from "./create-project-dialog";
import { CollectionList } from "./collection-list";
import { SavedSearchList } from "./saved-search-list";
import { ProjectMembers } from "./project-members";
import type { ProjectStatus } from "../types";

function statusBadgeVariant(
  status: ProjectStatus
): "default" | "destructive" {
  return status === "active" ? "default" : "destructive";
}

interface ProjectDetailProps {
  projectId: string;
}

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const router = useRouter();
  const { data: project, isLoading } = useProject(projectId);
  const archiveMutation = useArchiveProject();

  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  // --- Loading ---
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // --- Not found ---
  if (!project) {
    return (
      <div className="text-center text-muted-foreground py-12">
        <FolderKanban className="mx-auto h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4">Project not found.</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-4"
          onClick={() => router.push("/projects")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Projects
        </Button>
      </div>
    );
  }

  const isArchived = project.status === "archived";

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/projects")}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Projects
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
          <Badge variant={statusBadgeVariant(project.status as ProjectStatus)}>
            {project.status}
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          {!isArchived && (
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
          )}
        </div>
      </div>

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

      {/* Edit dialog */}
      <CreateProjectDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        project={project}
      />

      {/* Archive confirmation */}
      <AlertDialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive project?</AlertDialogTitle>
            <AlertDialogDescription>
              Archiving &ldquo;{project.name}&rdquo; will hide it from the
              active projects list. Collections and saved searches will be
              preserved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                archiveMutation.mutate(project.id, {
                  onSuccess: () => setArchiveOpen(false),
                });
              }}
              disabled={archiveMutation.isPending}
            >
              {archiveMutation.isPending ? "Archiving..." : "Archive"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
