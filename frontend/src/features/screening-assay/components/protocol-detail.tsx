"use client";

import { VisualizeButton } from "@/features/visualization/components/visualize-button";
import { CascadeDeleteDialog } from "@/shared/components/cascade-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
import { DetailTabsContent, DetailTabsList } from "@/shared/components/detail-tabs";
import { OwnerOrgLine } from "@/shared/components/owner-org-line";
import { ReturnToBarFromUrl } from "@/shared/components/return-to-bar";
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
import { Label } from "@/shared/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { canChangeOwner, useChangeOwner } from "@/shared/hooks/use-change-owner";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
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
import { type ReactNode, useEffect, useState } from "react";
import { useProtocolNamePreview } from "../hooks/use-protocol-name-preview";
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
import type { Protocol, ProtocolStatus } from "../types";
import { CorrectProtocolDialog } from "./correct-protocol-dialog";
import { CreateProtocolDialog } from "./create-protocol-dialog";
import { CreateRunDialog } from "./create-run-dialog";
import { ActivityTab, CurvesTab, DesignTab, FilesTab, OverviewTab, RunsTab } from "./detail-tabs";
import { DiscriminatorInput } from "./discriminator-input";
import { ProtocolCategoryInput } from "./protocol-category-input";
import { ProtocolNamePreview, useRequiredNameSlots } from "./protocol-name-preview";

// ---------------------------------------------------------------------------
// ProtocolDetail — tab shell
// ---------------------------------------------------------------------------

interface ProtocolDetailProps {
  protocolId: string;
}

export function ProtocolDetail({ protocolId }: ProtocolDetailProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const canCreate = useAuthzHasRole("editor");
  const { data: protocol, isLoading } = useProtocol(protocolId);
  const { data: me } = useCurrentUser();
  const changeOwner = useChangeOwner("protocols", protocolId);
  const publishMutation = usePublishProtocol();
  const retireMutation = useRetireProtocol();
  const versionMutation = useVersionProtocol();
  const updateMutation = useUpdateProtocol(protocolId);
  const deleteMutation = useDeleteProtocol();
  const lockMutation = useLockProtocol();
  const unlockMutation = useUnlockProtocol();

  const [hashTab, setHashTab] = useHashTab("overview");
  const hasCurves = protocol?.has_measured_curves === true;
  const [resultsView, setResultsView] = useState(hashTab === "curves" ? "curves" : "activity");
  const activeResultsView =
    hasCurves &&
    (hashTab === "curves" ||
      (hashTab !== "activity" && hashTab !== "results" && resultsView === "curves"))
      ? "curves"
      : "activity";
  const activeTab =
    hashTab === "design"
      ? "setup"
      : hashTab === "activity"
        ? "results"
        : hashTab === "curves"
          ? hasCurves
            ? "results"
            : "overview"
          : ["overview", "runs", "results", "setup", "files"].includes(hashTab)
            ? hashTab
            : "overview";

  useEffect(() => {
    if (hashTab === "curves") setResultsView("curves");
    if (hashTab === "activity" || hashTab === "results") setResultsView("activity");
  }, [hashTab]);

  const openResultsView = (view: string) => {
    setResultsView(view);
    setHashTab(view === "curves" ? "curves" : "results");
  };
  const setActiveTab = (tab: string) => {
    if (tab === "activity" || tab === "curves") openResultsView(tab);
    else if (tab === "results") openResultsView(activeResultsView);
    else setHashTab(tab === "design" ? "setup" : tab);
  };

  // Shared with Runs so comparing selected runs opens the same Results view.
  const [curveRunIds, setCurveRunIds] = useState<string[]>([]);

  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editCategory, setEditCategory] = useState("");
  const [editDiscriminator, setEditDiscriminator] = useState("");
  const [lockOpen, setLockOpen] = useState(false);
  const [lockReason, setLockReason] = useState("");
  const [lockMode, setLockMode] = useState<"lock" | "unlock">("lock");
  const [forceDeleteOpen, setForceDeleteOpen] = useState(false);
  const [correctOpen, setCorrectOpen] = useState(false);
  const [newAssayOpen, setNewAssayOpen] = useState(false);

  const query = { data: protocol, isLoading };

  const openEditDetails = (p: Protocol) => {
    setEditCategory(p.category ?? "");
    setEditDiscriminator(p.discriminator ?? "");
    setEditOpen(true);
  };
  // The discriminator is edited where the protocol's state allows: a draft's details, or a
  // correction on an unlocked published protocol. Locked and retired protocols cannot change it.
  const editName = (p: Protocol) =>
    p.is_locked
      ? undefined
      : p.status === "draft"
        ? () => openEditDetails(p)
        : p.status === "active"
          ? () => setCorrectOpen(true)
          : undefined;

  // Live name while editing a draft. Missing facts are fine on a draft (they only
  // block publishing); a clash or an invalid discriminator is not.
  const preview = useProtocolNamePreview(
    editOpen && protocol
      ? {
          category: editCategory || null,
          target_ids: protocol.targets.map((t) => t.id),
          ontology_annotations: protocol.ontology_annotations ?? {},
          discriminator: editDiscriminator.trim() || null,
          protocol_id: protocol.id,
        }
      : null,
  );
  const editNeeds = useRequiredNameSlots(editCategory);
  const draftSavable =
    !!preview.data &&
    !preview.data.clash &&
    !preview.data.needs_discriminator &&
    !preview.data.discriminator_error;

  return (
    <>
      <DetailShell
        compact
        query={query}
        backHref="/assays"
        backLabel="Back to Protocols"
        title={(p) => p.name}
        subtitle={(p) => (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {p.code && <span className="tabular-nums">{p.code}</span>}
            <OwnerOrgLine
              ownerOrgId={p.owner_org_id}
              canChange={canChangeOwner(me, p.created_by)}
              onSave={changeOwner.mutateAsync}
            />
          </span>
        )}
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
              <DropdownMenuItem key="edit" onClick={() => openEditDetails(p)}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit details
              </DropdownMenuItem>,
            );
          }

          // The server decides: a draft the caller created (or any draft, for
          // an admin) that no campaign, run, flag or template still uses.
          if (!locked && p.can_delete) {
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
              <DropdownMenuItem key="correct" onClick={() => setCorrectOpen(true)}>
                <Pencil className="mr-2 h-4 w-4" />
                Correct details…
              </DropdownMenuItem>,
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

          // Any protocol can seed a sibling assay (a draft cannot be versioned, so this is its
          // way to a copy); it is a create, so only roles that can create protocols see it.
          if (canCreate) {
            neutralItems.push(
              <DropdownMenuItem key="new-from" onClick={() => setNewAssayOpen(true)}>
                <Copy className="mr-2 h-4 w-4" />
                New protocol from this
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
                      Review permanent deletion…
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </>
          );
        }}
      >
        {(protocol) => (
          <>
            <ReturnToBarFromUrl protocolId={protocol.id} protocolCode={protocol.code} />
            <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-4">
              <DetailTabsList aria-label="Protocol sections">
                <TabsTrigger value="overview">
                  <LayoutDashboard className="h-4 w-4" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="runs">
                  <FlaskConical className="h-4 w-4" />
                  Runs
                </TabsTrigger>
                <TabsTrigger value="results">
                  <Activity className="h-4 w-4" />
                  Results
                </TabsTrigger>
                <TabsTrigger value="setup">
                  <Settings2 className="h-4 w-4" />
                  Setup
                </TabsTrigger>
                <TabsTrigger value="files">
                  <Paperclip className="h-4 w-4" />
                  Files
                </TabsTrigger>
              </DetailTabsList>

              <DetailTabsContent value="overview" activeValue={activeTab}>
                <OverviewTab
                  protocol={protocol}
                  protocolId={protocolId}
                  onTabChange={setActiveTab}
                  onEditName={editName(protocol)}
                />
              </DetailTabsContent>
              <DetailTabsContent value="runs" activeValue={activeTab}>
                <RunsTab
                  protocol={protocol}
                  protocolId={protocolId}
                  onCompareCurves={(ids) => {
                    setCurveRunIds(ids);
                    openResultsView("curves");
                  }}
                />
              </DetailTabsContent>
              <DetailTabsContent value="results" activeValue={activeTab}>
                <Tabs value={activeResultsView} onValueChange={openResultsView} className="gap-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <TabsList aria-label="Protocol result view">
                      <TabsTrigger value="activity">Compound activity</TabsTrigger>
                      {hasCurves && <TabsTrigger value="curves">Compare traces</TabsTrigger>}
                    </TabsList>
                    <VisualizeButton protocolId={protocol.id} />
                  </div>
                  <DetailTabsContent value="activity" activeValue={activeResultsView}>
                    <ActivityTab protocol={protocol} protocolId={protocolId} />
                  </DetailTabsContent>
                  {hasCurves && (
                    <DetailTabsContent value="curves" activeValue={activeResultsView}>
                      <CurvesTab
                        protocolId={protocolId}
                        runIds={curveRunIds}
                        onRunIdsChange={setCurveRunIds}
                      />
                    </DetailTabsContent>
                  )}
                </Tabs>
              </DetailTabsContent>
              <DetailTabsContent value="setup" activeValue={activeTab}>
                <DesignTab protocol={protocol} protocolId={protocolId} />
              </DetailTabsContent>
              <DetailTabsContent value="files" activeValue={activeTab}>
                <FilesTab protocolId={protocolId} />
              </DetailTabsContent>
            </Tabs>
          </>
        )}
      </DetailShell>

      {protocol && (
        <>
          <CorrectProtocolDialog
            protocol={protocol}
            open={correctOpen}
            onOpenChange={setCorrectOpen}
            onNewAssay={() => setNewAssayOpen(true)}
          />
          <CreateProtocolDialog
            open={newAssayOpen}
            onOpenChange={setNewAssayOpen}
            prefill={protocol}
          />
        </>
      )}

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
            <DialogDescription>
              The facts its name comes from. The method is edited on the Overview.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Category</Label>
              <ProtocolCategoryInput value={editCategory} onChange={setEditCategory} />
            </div>
            <div className="grid gap-2">
              <Label>Distinguished by{editNeeds.has("discriminator") ? "" : " (optional)"}</Label>
              <DiscriminatorInput
                value={editDiscriminator}
                onChange={setEditDiscriminator}
                base={preview.data?.base ?? null}
              />
            </div>
            <ProtocolNamePreview
              preview={preview.data}
              isFetching={preview.isFetching}
              code={protocol?.code}
            />
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                updateMutation.mutate(
                  {
                    category: editCategory || null,
                    discriminator: editDiscriminator.trim() || null,
                  },
                  { onSuccess: () => setEditOpen(false) },
                );
              }}
              disabled={!draftSavable || updateMutation.isPending}
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
              This will permanently delete &quot;{protocol?.name}&quot; ({protocol?.code}, v
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

      {/* Review permanent deletion… — admin only, driven from the Admin menu. */}
      {isAdmin && protocol && (
        <CascadeDeleteDialog
          entityType="protocol"
          entityId={protocolId}
          entityLabel={protocol.code ?? protocol.name}
          onDeleted={() => router.push("/assays")}
          open={forceDeleteOpen}
          onOpenChange={setForceDeleteOpen}
        />
      )}
    </>
  );
}
