"use client";

import { CascadeDeleteDialog } from "@/shared/components/cascade-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { useAuthzHasRole } from "@duar-auth/nextjs";
import {
  Activity,
  AlertTriangle,
  Archive,
  ChevronDown,
  Copy,
  FlaskConical,
  LayoutDashboard,
  Lock,
  LockOpen,
  Paperclip,
  Pencil,
  Plus,
  RotateCcw,
  Send,
  Settings2,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";
import {
  useDeleteProtocol,
  useLockProtocol,
  useProtocol,
  usePublishProtocol,
  useRetireProtocol,
  useUnlockProtocol,
  useUpdateProtocol,
  useVersionProtocol,
} from "../hooks/use-protocols";
import type { ProtocolStatus } from "../types";
import { CreateRunDialog } from "./create-run-dialog";
import { ActivityTab, DesignTab, FilesTab, OverviewTab, RunsTab } from "./detail-tabs";

// ---------------------------------------------------------------------------
// ProtocolDetail — tab shell
// ---------------------------------------------------------------------------

interface ProtocolDetailProps {
  protocolId: string;
}

export function ProtocolDetail({ protocolId }: ProtocolDetailProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const { data: protocol, isLoading } = useProtocol(protocolId);
  const publishMutation = usePublishProtocol();
  const retireMutation = useRetireProtocol();
  const versionMutation = useVersionProtocol();
  const updateMutation = useUpdateProtocol(protocolId);
  const deleteMutation = useDeleteProtocol();
  const lockMutation = useLockProtocol();
  const unlockMutation = useUnlockProtocol();

  const [activeTab, setActiveTab] = useHashTab("overview");

  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [lockOpen, setLockOpen] = useState(false);
  const [lockReason, setLockReason] = useState("");
  const [lockMode, setLockMode] = useState<"lock" | "unlock">("lock");
  const [forceDeleteOpen, setForceDeleteOpen] = useState(false);

  const query = { data: protocol, isLoading };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/assays"
        backLabel="Back to Protocols"
        title={(p) => p.name}
        breadcrumbTrail={() => [{ label: "Protocols", href: "/assays" }]}
        badge={(p) => ({ status: p.status })}
        notFoundMessage="Protocol not found."
        actions={(p) => {
          const s = p.status as ProtocolStatus;
          const locked = p.is_locked;

          // Frequent forward action stays a prominent button; everything
          // occasional moves into a "More" menu, and admin-only destructive
          // actions into a separate, role-gated menu. While locked, only the
          // unlock toggle is offered (plus New Run, which doesn't mutate
          // protocol metadata).
          const primary =
            s === "active" ? (
              <Button size="sm" onClick={() => setCreateRunOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                New Run
              </Button>
            ) : s === "draft" && !locked ? (
              <Button
                size="sm"
                onClick={() => publishMutation.mutate({ id: protocolId })}
                disabled={publishMutation.isPending}
              >
                <Send className="mr-2 h-4 w-4" />
                {publishMutation.isPending ? "Publishing..." : "Publish"}
              </Button>
            ) : null;

          const neutralItems: ReactNode[] = [];
          const destructiveItems: ReactNode[] = [];

          if (!locked && s === "draft") {
            neutralItems.push(
              <DropdownMenuItem
                key="edit"
                onClick={() => {
                  setEditName(p.name);
                  setEditDescription(p.description ?? "");
                  setEditCategory(p.category ?? "");
                  setEditOpen(true);
                }}
              >
                <Pencil className="mr-2 h-4 w-4" />
                Edit details
              </DropdownMenuItem>,
              <DropdownMenuItem
                key="duplicate"
                onClick={() => versionMutation.mutate({ id: protocolId })}
                disabled={versionMutation.isPending}
              >
                <Copy className="mr-2 h-4 w-4" />
                Duplicate
              </DropdownMenuItem>,
            );
            destructiveItems.push(
              <DropdownMenuItem
                key="delete"
                className="text-destructive focus:text-destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete
              </DropdownMenuItem>,
            );
          }

          if (!locked && s === "active") {
            neutralItems.push(
              <DropdownMenuItem
                key="version"
                onClick={() => versionMutation.mutate({ id: protocolId })}
                disabled={versionMutation.isPending}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                New Version
              </DropdownMenuItem>,
            );
            destructiveItems.push(
              <DropdownMenuItem
                key="retire"
                className="text-destructive focus:text-destructive"
                onClick={() =>
                  retireMutation.mutate({ id: protocolId, data: { reason: "Retired by user" } })
                }
                disabled={retireMutation.isPending}
              >
                <Archive className="mr-2 h-4 w-4" />
                Retire
              </DropdownMenuItem>,
            );
          }

          if (s !== "retired") {
            neutralItems.push(
              <DropdownMenuItem
                key="lock"
                onClick={() => {
                  setLockMode(locked ? "unlock" : "lock");
                  setLockReason("");
                  setLockOpen(true);
                }}
              >
                {locked ? (
                  <>
                    <LockOpen className="mr-2 h-4 w-4" />
                    Unlock
                  </>
                ) : (
                  <>
                    <Lock className="mr-2 h-4 w-4" />
                    Lock
                  </>
                )}
              </DropdownMenuItem>,
            );
          }

          const hasMore = neutralItems.length + destructiveItems.length > 0;

          return (
            <>
              {primary}
              {hasMore && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" variant="outline">
                      More
                      <ChevronDown className="ml-1.5 h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    {neutralItems}
                    {destructiveItems.length > 0 && neutralItems.length > 0 && (
                      <DropdownMenuSeparator />
                    )}
                    {destructiveItems}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              {isAdmin && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label="Admin actions"
                      title="Admin actions"
                    >
                      <ShieldAlert className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                      Danger zone
                    </DropdownMenuLabel>
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={() => setForceDeleteOpen(true)}
                    >
                      <AlertTriangle className="mr-2 h-4 w-4" />
                      Force delete (cascade)…
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </>
          );
        }}
      >
        {(protocol) => (
          <Tabs value={activeTab} onValueChange={setActiveTab}>
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
              <OverviewTab protocol={protocol} protocolId={protocolId} onTabChange={setActiveTab} />
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
        protocolControlLayouts={protocol?.control_layouts ?? null}
        conditionDefinitions={protocol?.condition_definitions ?? []}
        open={createRunOpen}
        onOpenChange={setCreateRunOpen}
      />

      {/* Lock / Unlock dialog — captures the audit-log reason. */}
      <Dialog open={lockOpen} onOpenChange={setLockOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{lockMode === "lock" ? "Lock Protocol" : "Unlock Protocol"}</DialogTitle>
            <DialogDescription>
              {lockMode === "lock"
                ? "Freeze the protocol's metadata. While locked, no edits, additions, or status changes are allowed until you unlock."
                : "Release the freeze so the protocol can be edited again. Reason is recorded in the audit log."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label>Reason</Label>
            <Textarea
              placeholder={
                lockMode === "lock"
                  ? "e.g. FDA submission window, locked for external review"
                  : "e.g. Review complete, resuming edits"
              }
              value={lockReason}
              onChange={(e) => setLockReason(e.target.value)}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                const mut = lockMode === "lock" ? lockMutation : unlockMutation;
                mut.mutate(
                  { id: protocolId, data: { reason: lockReason.trim() } },
                  { onSuccess: () => setLockOpen(false) },
                );
              }}
              disabled={!lockReason.trim() || lockMutation.isPending || unlockMutation.isPending}
            >
              {lockMode === "lock"
                ? lockMutation.isPending
                  ? "Locking..."
                  : "Lock"
                : unlockMutation.isPending
                  ? "Unlocking..."
                  : "Unlock"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Draft Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Protocol</DialogTitle>
            <DialogDescription>Update this draft protocol&apos;s metadata.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
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
                  { onSuccess: () => setEditOpen(false) },
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

      {/* Force delete (cascade) — admin only, driven from the Admin menu. */}
      {isAdmin && protocol && (
        <CascadeDeleteDialog
          entityType="protocol"
          entityId={protocolId}
          entityLabel={protocol.name}
          onDeleted={() => router.push("/assays")}
          open={forceDeleteOpen}
          onOpenChange={setForceDeleteOpen}
        />
      )}
    </>
  );
}
