"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ExternalLink,
  Beaker,
  FolderOpen,
  FolderKanban,
  Grid3X3,
  History,
  LayoutDashboard,
  Link2,
  Paperclip,
  ShieldAlert,
  TestTubes,
} from "lucide-react";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/shared/components/ui/tabs";
import { DetailShell } from "@/shared/components/detail-shell";
import { useMolecule } from "../hooks/use-molecules";
import {
  LIFECYCLE_LABELS,
  MOLECULE_TYPE_LABELS,
  type LifecycleStage,
  type MoleculeType,
  type StructureStatus,
} from "../types";
import {
  OverviewTab,
  BatchesTab,
  ActivityTab,
  CollectionsTab,
  PlatesTab,
  RelationshipsTab,
  HistoryTab,
  FilesTab,
  ProjectsTab,
  AdminOperationsTab,
} from "./detail-tabs";

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function structureStatusBadgeClass(status: StructureStatus): string {
  return status === "disclosed"
    ? "border-success/40 text-success"
    : "border-yellow-500/40 text-yellow-400";
}

// ---------------------------------------------------------------------------
// CompoundDetail
// ---------------------------------------------------------------------------

interface CompoundDetailProps {
  compoundId: string;
}

export function CompoundDetail({ compoundId }: CompoundDetailProps) {
  const router = useRouter();
  const query = useMolecule(compoundId);
  const isAdmin = useAuthzHasRole("admin");

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

  return (
    <DetailShell
      query={query}
      backHref="/compounds"
      backLabel="Back to Compounds"
      title={(m) => m.registration_number || m.name || "Compound"}
      badge={(m) => ({
        status: m.lifecycle_stage,
        label: LIFECYCLE_LABELS[m.lifecycle_stage as LifecycleStage] ?? m.lifecycle_stage,
      })}
      notFoundMessage="Compound not found."
    >
      {(mol) => {
        const isTombstone = !!mol.merged_into_id;
        return (
          <>
            {/* Extra badges + name below title */}
            <div className="-mt-3 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={structureStatusBadgeClass(mol.structure_status as StructureStatus)}>
                {mol.structure_status === "disclosed" ? "Disclosed" : "Undisclosed"}
              </Badge>
              <Badge variant="outline">
                {MOLECULE_TYPE_LABELS[mol.molecule_type as MoleculeType] ?? mol.molecule_type}
              </Badge>
              {mol.name && (
                <span className="text-lg text-muted-foreground">{mol.name}</span>
              )}
            </div>

            {/* Tombstone banner */}
            {isTombstone && (
              <div className="flex items-center gap-3 rounded-lg border border-yellow-500/40 bg-yellow-500/10 p-4">
                <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-yellow-400">
                    This compound has been merged.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    All data has been moved to the target compound.
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    router.push(`/compounds/${mol.merged_into_id}`);
                  }}
                >
                  View target
                  <ExternalLink className="ml-2 h-3 w-3" />
                </Button>
              </div>
            )}

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={handleTabChange}>
              <TabsList variant="line">
                <TabsTrigger value="overview">
                  <LayoutDashboard className="mr-1.5 h-4 w-4" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="batches">
                  <Beaker className="mr-1.5 h-4 w-4" />
                  Batches
                </TabsTrigger>
                <TabsTrigger value="activity">
                  <TestTubes className="mr-1.5 h-4 w-4" />
                  Activity
                </TabsTrigger>
                <TabsTrigger value="collections">
                  <FolderOpen className="mr-1.5 h-4 w-4" />
                  Collections
                </TabsTrigger>
                <TabsTrigger value="projects">
                  <FolderKanban className="mr-1.5 h-4 w-4" />
                  Projects
                </TabsTrigger>
                <TabsTrigger value="plates">
                  <Grid3X3 className="mr-1.5 h-4 w-4" />
                  Plates
                </TabsTrigger>
                <TabsTrigger value="relationships">
                  <Link2 className="mr-1.5 h-4 w-4" />
                  Relationships
                </TabsTrigger>
                <TabsTrigger value="files">
                  <Paperclip className="mr-1.5 h-4 w-4" />
                  Files
                </TabsTrigger>
                <TabsTrigger value="history">
                  <History className="mr-1.5 h-4 w-4" />
                  History
                </TabsTrigger>
                {isAdmin && !isTombstone && (
                  <TabsTrigger value="admin">
                    <ShieldAlert className="mr-1.5 h-4 w-4" />
                    Admin
                  </TabsTrigger>
                )}
              </TabsList>

              <TabsContent value="overview">
                <OverviewTab molecule={mol} compoundId={compoundId} />
              </TabsContent>

              <TabsContent value="batches">
                <BatchesTab
                  moleculeId={compoundId}
                  moleculeMw={mol.descriptors?.molecular_weight ?? undefined}
                />
              </TabsContent>

              <TabsContent value="activity">
                <ActivityTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="collections">
                <CollectionsTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="projects">
                <ProjectsTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="plates">
                <PlatesTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="relationships">
                <RelationshipsTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="files">
                <FilesTab moleculeId={compoundId} />
              </TabsContent>

              <TabsContent value="history">
                <HistoryTab moleculeId={compoundId} molecule={mol} />
              </TabsContent>

              {isAdmin && !isTombstone && (
                <TabsContent value="admin">
                  <AdminOperationsTab moleculeId={compoundId} />
                </TabsContent>
              )}
            </Tabs>
          </>
        );
      }}
    </DetailShell>
  );
}
