"use client";

import { TagTable } from "@/features/tagging/components/tag-table";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { formatDate } from "@/shared/lib/format-date";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { Beaker, Clock, FlaskConical, Target } from "lucide-react";
import { useState } from "react";
import { useProtocolCollectionCoverage } from "../../hooks/use-protocol-collection-coverage";
import { useProtocolStats } from "../../hooks/use-protocol-stats";
import {
  PLATE_FORMAT_LABELS,
  PROTOCOL_TYPE_LABELS,
  type PlateFormat,
  type Protocol,
  type ProtocolType,
} from "../../types";
import { CoverageBar } from "../coverage-bar";
import { CoverageGapDialog } from "../coverage-gap-dialog";

// ---------------------------------------------------------------------------
// Z' quality badge helper
// ---------------------------------------------------------------------------

function zPrimeBadge(zPrime: number | null) {
  if (zPrime == null) return null;
  if (zPrime >= 0.5) {
    return (
      <Badge className="border-success/40 bg-success/10 text-success">
        Z&apos; {zPrime.toFixed(2)} — Excellent
      </Badge>
    );
  }
  if (zPrime >= 0) {
    return (
      <Badge className="border-yellow-500/40 bg-yellow-500/10 text-yellow-400">
        Z&apos; {zPrime.toFixed(2)} — Marginal
      </Badge>
    );
  }
  return (
    <Badge className="border-destructive/40 bg-destructive/10 text-destructive">
      Z&apos; {zPrime.toFixed(2)} — Poor
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Stats card
// ---------------------------------------------------------------------------

function StatsCard({
  icon: Icon,
  label,
  value,
  subtext,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  subtext?: string;
  onClick?: () => void;
}) {
  return (
    <Card
      className={onClick ? "cursor-pointer hover:border-primary/50 transition-colors" : undefined}
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-4 p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold tabular-nums">{value}</p>
          {subtext && <p className="text-xs text-muted-foreground">{subtext}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// OverviewTab
// ---------------------------------------------------------------------------

interface OverviewTabProps {
  protocol: Protocol;
  protocolId: string;
  onTabChange: (tab: string) => void;
}

export function OverviewTab({ protocol, protocolId, onTabChange }: OverviewTabProps) {
  const { data: stats, isLoading } = useProtocolStats(protocolId);
  const { data: coverage } = useProtocolCollectionCoverage(protocolId);
  const canEditTags = useAuthzHasRole("editor");
  const [gap, setGap] = useState<{ path: string; name: string } | null>(null);

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : stats ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatsCard
            icon={FlaskConical}
            label="Runs"
            value={stats.run_counts.total}
            subtext={
              stats.run_counts.in_progress > 0
                ? `${stats.run_counts.in_progress} in progress`
                : undefined
            }
            onClick={() => onTabChange("runs")}
          />
          <StatsCard
            icon={Beaker}
            label="Compounds"
            value={stats.compound_count}
            onClick={() => onTabChange("activity")}
          />
          <StatsCard
            icon={Target}
            label="Hits"
            value={stats.hit_criteria_applied ? (stats.hit_count ?? 0) : "\u2014"}
            subtext={!stats.hit_criteria_applied ? "No criteria set" : undefined}
            onClick={() => onTabChange("activity")}
          />
          <StatsCard
            icon={Clock}
            label="Pending Approval"
            value={stats.run_counts.completed}
            onClick={() => onTabChange("runs")}
          />
        </div>
      ) : null}

      {/* Latest Run Card */}
      <Card>
        <CardHeader>
          <CardTitle>Latest Run</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : stats?.latest_run ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div>
                  <p className="font-medium">{formatDate(stats.latest_run.run_date)}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge status={stats.latest_run.status} />
                    {stats.latest_run.plate_format && (
                      <Badge variant="outline">
                        {PLATE_FORMAT_LABELS[stats.latest_run.plate_format as PlateFormat] ??
                          stats.latest_run.plate_format}
                      </Badge>
                    )}
                    {stats.latest_run.plate_count > 0 && (
                      <span className="text-sm text-muted-foreground">
                        {stats.latest_run.plate_count} plate
                        {stats.latest_run.plate_count !== 1 ? "s" : ""}
                      </span>
                    )}
                    {stats.latest_run.compound_count > 0 && (
                      <span className="text-sm text-muted-foreground">
                        {stats.latest_run.compound_count} compound
                        {stats.latest_run.compound_count !== 1 ? "s" : ""}
                      </span>
                    )}
                    {zPrimeBadge(stats.latest_run.z_prime ?? null)}
                  </div>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => onTabChange("runs")}>
                View Runs
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No runs yet. Create a run from the Runs tab.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Coverage */}
      {coverage && coverage.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Coverage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {coverage.map((c) => (
              <CoverageBar
                key={c.id}
                coverage={c}
                runCount={c.run_count}
                onViewGap={() =>
                  setGap({ path: `/protocols/${protocolId}/collections/${c.id}`, name: c.name })
                }
              />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Details Card */}
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {protocol.description && (
            <p className="text-sm text-muted-foreground">{protocol.description}</p>
          )}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground">Type</p>
              <p className="font-medium">
                {PROTOCOL_TYPE_LABELS[protocol.protocol_type as ProtocolType] ??
                  protocol.protocol_type}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Category</p>
              <p className="font-medium">{protocol.category ?? "\u2014"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Version</p>
              <p className="font-medium">{protocol.protocol_version}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Readouts</p>
              <p className="font-medium">{protocol.readout_definitions.length}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tags */}
      <TagTable entity="protocols" entityId={protocolId} canEdit={canEditTags} />

      {gap && (
        <CoverageGapDialog
          open
          onOpenChange={(o) => !o && setGap(null)}
          gapBasePath={gap.path}
          collectionName={gap.name}
        />
      )}
    </div>
  );
}
