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
import type { CampaignResponse } from "../../types";

const SECTION_HEADING = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

interface LibrariesSectionProps {
  campaign: CampaignResponse;
  readOnly: boolean;
}

export function LibrariesSection({ campaign, readOnly }: LibrariesSectionProps) {
  const qc = useQueryClient();
  const { data: coverage, isLoading } = useCampaignCollectionCoverage(campaign.id);
  const addLibrary = useAddCampaignCollection(campaign.id);
  const removeLibrary = useRemoveCampaignCollection(campaign.id);
  const pending = addLibrary.isPending || removeLibrary.isPending;
  const [gap, setGap] = useState<{ collectionId: string; name: string } | null>(null);

  const libraries = coverage ?? [];
  const hasSeedRuns = campaign.seed_runs.length > 0;

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
              <CoverageBar
                key={c.id}
                coverage={c}
                onViewGap={() => setGap({ collectionId: c.id, name: c.name })}
              />
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
