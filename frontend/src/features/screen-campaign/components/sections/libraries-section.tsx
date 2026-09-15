"use client";

/**
 * LibrariesSection — the libraries this campaign screened, and how much of
 * each it read.
 *
 * One CoverageBar per linked collection: covered / total of today's
 * membership, where "covered" means the member has a readout in one of the
 * campaign's seed runs. "N remaining" opens the shared CoverageGapDialog on
 * the campaign's own gap endpoint, so the unscreened compounds render as the
 * same molecule cards the run and protocol surfaces use.
 *
 * A campaign with no seed runs (built from collections, another campaign, or
 * by hand) reads 0 everywhere — nothing was screened *in this campaign* — so
 * the empty-seed-run case says so rather than letting a row of zeroes imply
 * a failed screen.
 *
 * Under each bar, the campaign's stages counted over that library's rows —
 * which deck the hits came from. `tested` is the stage population minus the
 * rows with no reading and the ones still awaiting a manual call, so a hit
 * rate reads off the two numbers directly.
 */

import { CollectionMultiSelect } from "@/features/screening-assay/components/collection-multi-select";
import { CoverageBar } from "@/features/screening-assay/components/coverage-bar";
import { CoverageGapDialog } from "@/features/screening-assay/components/coverage-gap-dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import {
  invalidateCampaignCollectionQueries,
  useAddCampaignCollection,
  useCampaignCollectionCoverage,
  useRemoveCampaignCollection,
} from "../../hooks/use-campaign-collections";
import type { CampaignResponse, CollectionStageCountsResponse } from "../../types";

const SECTION_HEADING = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

interface LibrariesSectionProps {
  campaign: CampaignResponse;
  readOnly: boolean;
}

export function LibrariesSection({ campaign, readOnly }: LibrariesSectionProps) {
  const qc = useQueryClient();
  // Stage counts ride along with the coverage read (one campaign evaluation
  // for every library, server-side).
  const { data: coverage, isLoading } = useCampaignCollectionCoverage(campaign.id, true);
  const addLibrary = useAddCampaignCollection(campaign.id);
  const removeLibrary = useRemoveCampaignCollection(campaign.id);
  const pending = addLibrary.isPending || removeLibrary.isPending;
  const [gap, setGap] = useState<{ collectionId: string; name: string } | null>(null);

  const libraries = coverage ?? [];
  const hasSeedRuns = campaign.seed_runs.length > 0;
  const stageNameById = new Map(campaign.stages.map((s) => [s.id, s.name] as const));

  const apply = async (ids: string[]) => {
    const current = libraries.map((c) => c.id);
    try {
      await Promise.all([
        ...ids.filter((id) => !current.includes(id)).map((id) => addLibrary.mutateAsync(id)),
        ...current.filter((id) => !ids.includes(id)).map((id) => removeLibrary.mutateAsync(id)),
      ]);
    } catch {
      // surfaced by the mutations' error toasts
    } finally {
      await invalidateCampaignCollectionQueries(qc, campaign.id);
    }
  };

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Libraries</h2>
        {!readOnly && (
          <Popover>
            <PopoverTrigger className={ADD_PILL}>
              <Plus className="h-3 w-3" />
              Library
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80">
              <CollectionMultiSelect
                value={libraries.map((c) => c.id)}
                projectIds={campaign.project_id ? [campaign.project_id] : undefined}
                onChange={apply}
                disabled={pending}
                placeholder="Add a library…"
              />
            </PopoverContent>
          </Popover>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading coverage…</p>
      ) : libraries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {readOnly
            ? "No libraries were named for this campaign."
            : "No libraries yet — name the decks this campaign screened to see how much of each was read."}
        </p>
      ) : (
        <>
          <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
            {libraries.map((c) => (
              <div key={c.id}>
                <CoverageBar
                  coverage={c}
                  onViewGap={() => setGap({ collectionId: c.id, name: c.name })}
                />
                <StageLines stages={c.stages ?? []} nameById={stageNameById} />
              </div>
            ))}
          </div>
          {!hasSeedRuns && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              This campaign was not built from runs, so nothing counts as screened in it.
            </p>
          )}
        </>
      )}

      {gap && (
        <CoverageGapDialog
          open
          onOpenChange={(o) => !o && setGap(null)}
          gapBasePath={`/campaigns/${campaign.id}/collections/${gap.collectionId}`}
          collectionName={gap.name}
        />
      )}
    </section>
  );
}

/** The campaign's funnel for one library: hits and tested per stage.
 *
 *  Every stage is listed, including the ones this library never reached — a
 *  zero row is the answer to "did anything of ours get that far", not noise. */
function StageLines({
  stages,
  nameById,
}: {
  stages: CollectionStageCountsResponse[];
  nameById: Map<string, string>;
}) {
  if (stages.length === 0) return null;
  return (
    <dl className="mt-1.5 space-y-0.5">
      {stages.map(({ stage_id, counts }) => {
        const tested = counts.population - counts.untested - counts.pending;
        return (
          <div
            key={stage_id}
            className="flex items-baseline justify-between gap-2 text-[11px] text-muted-foreground"
          >
            <dt className="truncate">{nameById.get(stage_id) ?? "Stage"}</dt>
            <dd className="shrink-0 tabular-nums">
              {counts.hit.toLocaleString("en-US")} {counts.hit === 1 ? "hit" : "hits"} /{" "}
              {tested.toLocaleString("en-US")} tested
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
