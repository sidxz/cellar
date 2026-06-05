"use client";

import { TagTable } from "@/features/tagging/components/tag-table";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, FileText, Lock, Pencil, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { MemberName } from "@/shared/components/entity-name";
import { useUpdateCampaignApiV1CampaignsCampaignIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { showError } from "@/shared/lib/toast";
import { campaignKeys } from "../../hooks/use-campaigns";
import type { CampaignResponse } from "../../types";
import { CampaignStatusChip } from "../campaign-status-chip";

interface HeaderStripProps {
  campaign: CampaignResponse;
  /** Show draft-mode action buttons (Refresh / Preview / Close & Sign). */
  isDraft: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
  onPreview: () => void;
  onCloseAndSign: () => void;

  // ── Closed-mode metadata + actions (optional; surfaced when !isDraft) ────────
  /** ISO timestamp from `campaign.closed_at` (when status is closed/superseded). */
  closedAt?: string | null;
  /** UUID from `campaign.closed_by`. Name resolution via Sentinel is a known
   *  follow-up (A2); show the first 8 chars as a stable placeholder. */
  closedBy?: string | null;
  /** UUID from `campaign.signature_id`. Per the no-UUID rule we show a slice. */
  signatureId?: string | null;
  /** UUID from `campaign.supersedes_campaign_id`. Renders a link if present. */
  supersedesId?: string | null;
  /** UUID from `campaign.superseded_by_campaign_id`. Renders the amber banner. */
  supersededBy?: string | null;
  /** Project id — needed to build supersede links. */
  projectId?: string;

  /** Download Published JSON action. */
  onDownload?: () => void;
  downloadDisabled?: boolean;
  downloadLabel?: string;
  /** Supersede action — only relevant for closed campaigns that aren't yet superseded. */
  onSupersede?: () => void;
  /** Whether the current user can edit tags on this campaign. */
  canEditTags?: boolean;
}

export function HeaderStrip({
  campaign,
  isDraft,
  refreshing,
  onRefresh,
  onPreview,
  onCloseAndSign,
  closedAt,
  closedBy,
  signatureId,
  supersedesId,
  supersededBy,
  projectId,
  onDownload,
  downloadDisabled,
  downloadLabel,
  onSupersede,
  canEditTags = false,
}: HeaderStripProps) {
  const channelCount = campaign.channels?.length ?? 0;
  const compoundCount = campaign.results?.length ?? 0;

  // Closed-metadata muted line. Resolves closed_by (Sentinel UUID) to the
  // member's display name via <MemberName />; the e-signature UUID is hidden
  // from the visible header and surfaced only via a hover tooltip so it
  // stays auditable without polluting the chemist's reading line.
  const hasClosedMeta = !!(closedAt || closedBy || signatureId);

  return (
    <header className="flex flex-col gap-1 border-b px-6 py-4">
      {/* Superseded-by banner (closed-mode only) */}
      {!isDraft && supersededBy && projectId && (
        <div className="mb-2 flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            This campaign was superseded by{" "}
            <Link
              href={`/projects/${projectId}/campaigns/${supersededBy}`}
              className="font-medium underline underline-offset-2 hover:opacity-80"
            >
              a newer campaign
            </Link>
            .
          </span>
        </div>
      )}

      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{campaign.name}</h1>
        <CampaignStatusChip status={campaign.status} />
        <Badge variant="outline" className="text-xs">
          {channelCount} {channelCount === 1 ? "channel" : "channels"}
        </Badge>
        <Badge variant="outline" className="text-xs">
          {compoundCount} {compoundCount === 1 ? "compound" : "compounds"}
        </Badge>
        {!isDraft && supersedesId && projectId && (
          <Badge variant="outline" className="text-xs gap-1">
            Supersedes{" "}
            <Link
              href={`/projects/${projectId}/campaigns/${supersedesId}`}
              className="underline underline-offset-2 hover:opacity-80"
            >
              prior campaign
            </Link>
          </Badge>
        )}

        <div className="ml-auto flex items-center gap-2">
          {isDraft ? (
            <>
              <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
                <RefreshCw className={refreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                Refresh
              </Button>
              <Button variant="outline" size="sm" onClick={onPreview}>
                <FileText className="h-4 w-4" />
                Preview as published
              </Button>
              <Button size="sm" onClick={onCloseAndSign}>
                <Lock className="h-4 w-4" />
                Close &amp; Sign
              </Button>
            </>
          ) : (
            <>
              {onDownload && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onDownload}
                  disabled={downloadDisabled}
                >
                  <Download className="h-4 w-4" />
                  {downloadLabel ?? "Download JSON"}
                </Button>
              )}
              {onSupersede && (
                <Button variant="outline" size="sm" onClick={onSupersede}>
                  <Lock className="h-4 w-4" />
                  Supersede
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      <DescriptionRow campaign={campaign} editable={isDraft} />
      {!isDraft && hasClosedMeta && (
        <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-x-2">
          {closedAt && (
            <span>
              Closed {/* inline: custom date format — dateStyle:"medium" + timeStyle:"short" */}
              {new Date(closedAt).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </span>
          )}
          {closedBy && (
            <span>
              by <MemberName id={closedBy} />
            </span>
          )}
          {signatureId && (
            <span
              className="cursor-help underline decoration-dotted decoration-muted-foreground/40 underline-offset-2"
              title={`E-signature ID (audit only): ${signatureId}`}
            >
              Signed
            </span>
          )}
        </p>
      )}
      <TagTable entity="campaigns" entityId={campaign.id} canEdit={canEditTags} />
    </header>
  );
}

/**
 * Click-to-edit description line. Renders muted text by default with a
 * pencil-edit affordance; switches to a textarea with explicit Save /
 * Cancel buttons on click. ⌘/Ctrl+Enter still saves and Escape still
 * cancels for keyboard-first chemists, but the buttons are the primary
 * commit path. Read-only mode skips the affordance.
 */
function DescriptionRow({
  campaign,
  editable,
}: {
  campaign: CampaignResponse;
  editable: boolean;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(campaign.description ?? "");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Re-sync local draft whenever the parent campaign refresh brings new data
  // (e.g. after another mutation invalidates and refetches). Avoids leaving a
  // stale unsaved draft in the textbox when the canonical value updates.
  useEffect(() => {
    if (!editing) setDraft(campaign.description ?? "");
  }, [campaign.description, editing]);

  // Focus the textarea + move caret to end whenever we enter edit mode.
  useEffect(() => {
    if (editing && textareaRef.current) {
      const ta = textareaRef.current;
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
  }, [editing]);

  const mutation = useUpdateCampaignApiV1CampaignsCampaignIdPatch({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        setEditing(false);
      },
      onError: (err) => {
        const msg = err instanceof Error ? err.message : String(err);
        showError(`Couldn't save description: ${msg}`);
      },
    },
  });

  function commit() {
    const trimmed = draft.trim();
    const current = campaign.description ?? "";
    if (trimmed === current.trim()) {
      setEditing(false);
      return;
    }
    mutation.mutate({
      campaignId: campaign.id,
      data: { description: trimmed === "" ? null : trimmed },
    });
  }

  function cancel() {
    setDraft(campaign.description ?? "");
    setEditing(false);
  }

  if (editing) {
    const dirty = draft.trim() !== (campaign.description ?? "").trim();
    return (
      <div className="flex flex-col gap-2">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              commit();
            }
          }}
          rows={3}
          disabled={mutation.isPending}
          placeholder="Describe what this campaign is for…"
          className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
        />
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={cancel}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button type="button" size="sm" onClick={commit} disabled={mutation.isPending || !dirty}>
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    );
  }

  const hasDescription = !!campaign.description?.trim();
  if (!hasDescription && !editable) return null;

  // Notion-style: the description itself is the click target. No corner-
  // floating pencil. Hover gives a subtle background + a faint pencil glyph
  // inline at the end of the text so the affordance is discoverable without
  // looking like a settings cog.
  if (!editable) {
    return <p className="text-sm text-muted-foreground">{campaign.description}</p>;
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      aria-label={hasDescription ? "Edit description" : "Add description"}
      className="group -ml-1 inline-flex max-w-full items-start gap-1.5 rounded-md px-1 py-0.5 text-left hover:bg-muted/50 focus:bg-muted/60 focus:outline-none transition-colors"
    >
      <span
        className={`text-sm ${
          hasDescription ? "text-muted-foreground" : "text-muted-foreground/60 italic"
        }`}
      >
        {hasDescription ? campaign.description : "Add a description…"}
      </span>
      <Pencil className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
    </button>
  );
}
