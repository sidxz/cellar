"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  AlertTriangle,
  FlaskConical,
  ExternalLink,
  Beaker,
  FolderOpen,
  FolderKanban,
  Grid3X3,
  History,
  LayoutDashboard,
  Link2,
  Paperclip,
  TestTubes,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/shared/components/ui/tabs";
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
} from "./detail-tabs";

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function lifecycleBadgeVariant(
  stage: LifecycleStage
): "default" | "secondary" | "destructive" | "outline" {
  switch (stage) {
    case "active":
    case "hit":
    case "lead":
      return "default";
    case "preclinical_candidate":
    case "development_candidate":
      return "secondary";
    case "deprioritized":
    case "archived":
      return "destructive";
    default:
      return "outline";
  }
}

function structureStatusBadgeClass(status: StructureStatus): string {
  return status === "disclosed"
    ? "border-emerald-500/40 text-emerald-400"
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
  const { data: mol, isLoading } = useMolecule(compoundId);

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

  // --- Loading ---
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  // --- Not found ---
  if (!mol) {
    return (
      <div className="text-center text-muted-foreground py-12">
        <FlaskConical className="mx-auto h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4">Compound not found.</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-4"
          onClick={() => router.back()}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to compounds
        </Button>
      </div>
    );
  }

  const isTombstone = !!mol.merged_into_id;

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.back()}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to compounds
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {mol.registration_number}
            </h1>
            <Badge variant={lifecycleBadgeVariant(mol.lifecycle_stage as LifecycleStage)}>
              {LIFECYCLE_LABELS[mol.lifecycle_stage as LifecycleStage] ?? mol.lifecycle_stage}
            </Badge>
            <Badge variant="outline" className={structureStatusBadgeClass(mol.structure_status as StructureStatus)}>
              {mol.structure_status === "disclosed" ? "Disclosed" : "Undisclosed"}
            </Badge>
            <Badge variant="outline">
              {MOLECULE_TYPE_LABELS[mol.molecule_type as MoleculeType] ?? mol.molecule_type}
            </Badge>
          </div>
          {mol.name && (
            <p className="mt-1 text-lg text-muted-foreground">{mol.name}</p>
          )}
        </div>
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
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab molecule={mol} compoundId={compoundId} />
        </TabsContent>

        <TabsContent value="batches">
          <BatchesTab moleculeId={compoundId} />
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
      </Tabs>
    </div>
  );
}
