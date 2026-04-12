"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  Archive,
  Copy,
  FlaskConical,
  LayoutDashboard,
  Paperclip,
  Pencil,
  RotateCcw,
  Send,
  Settings2,
  Trash2,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/shared/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import {
  useProtocol,
  usePublishProtocol,
  useRetireProtocol,
  useVersionProtocol,
  useUpdateProtocol,
  useDeleteProtocol,
} from "../hooks/use-protocols";
import { CreateRunDialog } from "./create-run-dialog";
import { OverviewTab, ActivityTab, DesignTab, RunsTab, FilesTab } from "./detail-tabs";
import type { ProtocolStatus } from "../types";

// ---------------------------------------------------------------------------
// ProtocolDetail — tab shell
// ---------------------------------------------------------------------------

interface ProtocolDetailProps {
  protocolId: string;
}

export function ProtocolDetail({ protocolId }: ProtocolDetailProps) {
  const router = useRouter();
  const { data: protocol, isLoading } = useProtocol(protocolId);
  const publishMutation = usePublishProtocol();
  const retireMutation = useRetireProtocol();
  const versionMutation = useVersionProtocol();
  const updateMutation = useUpdateProtocol(protocolId);
  const deleteMutation = useDeleteProtocol();

  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== "undefined") {
      return window.location.hash.slice(1) || "overview";
    }
    return "overview";
  });

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    window.history.replaceState(null, "", `#${value}`);
  };

  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("");

  const query = { data: protocol, isLoading };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/assays"
        backLabel="Back to Protocols"
        title={(p) => p.name}
        badge={(p) => ({ status: p.status })}
        notFoundMessage="Protocol not found."
        actions={(p) => {
          const s = p.status as ProtocolStatus;
          return (
            <>
              {s === "draft" && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditName(p.name);
                      setEditDescription(p.description ?? "");
                      setEditCategory(p.category ?? "");
                      setEditOpen(true);
                    }}
                  >
                    <Pencil className="mr-2 h-4 w-4" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => versionMutation.mutate(protocolId)}
                    disabled={versionMutation.isPending}
                  >
                    <Copy className="mr-2 h-4 w-4" />
                    {versionMutation.isPending ? "Duplicating..." : "Duplicate"}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => setDeleteOpen(true)}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => publishMutation.mutate(protocolId)}
                    disabled={publishMutation.isPending}
                  >
                    <Send className="mr-2 h-4 w-4" />
                    {publishMutation.isPending ? "Publishing..." : "Publish"}
                  </Button>
                </>
              )}
              {s === "active" && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => versionMutation.mutate(protocolId)}
                    disabled={versionMutation.isPending}
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    {versionMutation.isPending ? "Creating..." : "New Version"}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() =>
                      retireMutation.mutate({
                        id: protocolId,
                        reason: "Retired by user",
                      })
                    }
                    disabled={retireMutation.isPending}
                  >
                    <Archive className="mr-2 h-4 w-4" />
                    {retireMutation.isPending ? "Retiring..." : "Retire"}
                  </Button>
                </>
              )}
            </>
          );
        }}
      >
        {(protocol) => (
          <Tabs value={activeTab} onValueChange={handleTabChange}>
            <TabsList variant="line">
              <TabsTrigger value="overview">
                <LayoutDashboard className="mr-1.5 h-4 w-4" />
                Overview
              </TabsTrigger>
              <TabsTrigger value="activity">
                <Activity className="mr-1.5 h-4 w-4" />
                Activity
              </TabsTrigger>
              <TabsTrigger value="design">
                <Settings2 className="mr-1.5 h-4 w-4" />
                Design
              </TabsTrigger>
              <TabsTrigger value="runs">
                <FlaskConical className="mr-1.5 h-4 w-4" />
                Runs
              </TabsTrigger>
              <TabsTrigger value="files">
                <Paperclip className="mr-1.5 h-4 w-4" />
                Files
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview">
              <OverviewTab
                protocol={protocol}
                protocolId={protocolId}
                onTabChange={handleTabChange}
              />
            </TabsContent>
            <TabsContent value="activity">
              <ActivityTab protocol={protocol} protocolId={protocolId} />
            </TabsContent>
            <TabsContent value="design">
              <DesignTab protocol={protocol} protocolId={protocolId} />
            </TabsContent>
            <TabsContent value="runs">
              <RunsTab protocol={protocol} protocolId={protocolId} />
            </TabsContent>
            <TabsContent value="files">
              <FilesTab protocolId={protocolId} />
            </TabsContent>
          </Tabs>
        )}
      </DetailShell>

      <CreateRunDialog
        protocolId={protocolId}
        open={createRunOpen}
        onOpenChange={setCreateRunOpen}
      />

      {/* Edit Draft Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Protocol</DialogTitle>
            <DialogDescription>
              Update this draft protocol&apos;s metadata.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Optional — describe the assay procedure, controls, and acceptance criteria"
                rows={4}
              />
            </div>
            <div className="grid gap-2">
              <Label>Category</Label>
              <Input
                value={editCategory}
                onChange={(e) => setEditCategory(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                updateMutation.mutate(
                  {
                    name: editName || undefined,
                    description: editDescription || null,
                    category: editCategory || null,
                  },
                  { onSuccess: () => setEditOpen(false) }
                );
              }}
              disabled={!editName.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Draft Protocol</DialogTitle>
            <DialogDescription>
              This will permanently delete &quot;{protocol?.name}&quot; (v
              {protocol?.protocol_version}). This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                deleteMutation.mutate(protocolId, {
                  onSuccess: () => {
                    router.push("/assays");
                  },
                });
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
