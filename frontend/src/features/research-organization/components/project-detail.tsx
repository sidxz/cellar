"use client";

import { useState } from "react";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { Archive, FolderKanban, Library, Pencil, Plus, TestTubes } from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { TagTable } from "@/features/tagging/components/tag-table";
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
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/shared/components/ui/tabs";
import { DetailShell } from "@/shared/components/detail-shell";
import { MemberName } from "@/shared/components/entity-name";
import { useProject, useArchiveProject } from "../hooks/use-projects";
import { ProtocolList } from "@/features/screening-assay";
import { CreateProjectDialog } from "./create-project-dialog";
import { AddProtocolDialog } from "./add-protocol-dialog";
import { CollectionList } from "./collection-list";
import { SavedSearchList } from "./saved-search-list";
import { ProjectMembers } from "./project-members";
import { CampaignList } from "@/features/screen-campaign";

interface ProjectDetailProps {
  projectId: string;
}

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const query = useProject(projectId);
  const archiveMutation = useArchiveProject();
  const canEditTags = useAuthzHasRole("editor");

  const [tab, setTab] = useHashTab("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [addProtocolOpen, setAddProtocolOpen] = useState(false);

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
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList variant="line">
              <TabsTrigger value="overview">
                <FolderKanban className="mr-1.5 size-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="protocols">
                <TestTubes className="mr-1.5 size-4" />
                Protocols
              </TabsTrigger>
              <TabsTrigger value="collections">
                <Library className="mr-1.5 size-4" />
                Collections
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
              {/* Details */}
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

              {/* Campaigns */}
              <Card>
                <CardHeader>
                  <CardTitle>Campaigns</CardTitle>
                </CardHeader>
                <CardContent>
                  <CampaignList projectId={projectId} />
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
                  <CardTitle>Members</CardTitle>
                </CardHeader>
                <CardContent>
                  <ProjectMembers projectId={projectId} />
                </CardContent>
              </Card>

              {/* Tags */}
              <TagTable entity="projects" entityId={projectId} canEdit={canEditTags} />
            </TabsContent>

            <TabsContent value="protocols" className="space-y-3">
              <div className="flex justify-end">
                <Button size="sm" onClick={() => setAddProtocolOpen(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Add Protocol
                </Button>
              </div>
              <ProtocolList projectId={projectId} />
            </TabsContent>

            <TabsContent value="collections">
              <CollectionList projectId={projectId} />
            </TabsContent>
          </Tabs>
        )}
      </DetailShell>

      {/* Add protocol to project */}
      <AddProtocolDialog
        projectId={projectId}
        open={addProtocolOpen}
        onOpenChange={setAddProtocolOpen}
      />

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
