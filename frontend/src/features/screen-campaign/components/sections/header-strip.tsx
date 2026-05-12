"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import {
  RefreshCw,
  FileText,
  Lock,
  Download,
  AlertTriangle,
  Pencil,
} from "lucide-react";
import Link from "next/link";

import { useUpdateCampaignApiV1CampaignsCampaignIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { showError } from "@/shared/lib/toast";
import type { CampaignResponse } from "../../types";
import { CampaignStatusChip } from "../campaign-status-chip";
import { campaignKeys } from "../../lib/hooks";

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
}: HeaderStripProps) {
  const channelCount = campaign.channels?.length ?? 0;
  const compoundCount = campaign.results?.length ?? 0;

  // Compose the closed-metadata muted line. Each piece is optional.
  const closedMetaParts: string[] = [];
  if (closedAt) {
    closedMetaParts.push(
      `Closed ${new Date(closedAt).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })}`,
    );
  }
  if (closedBy) {
    // closed_by is a Sentinel user UUID. Until name resolution lands, show a
    // stable 8-char slice so the line is debuggable but never a full UUID.
    closedMetaParts.push(`by ${closedBy.slice(0, 8)}`);
  }
  if (signatureId) {
    closedMetaParts.push(`Signature ${signatureId.slice(0, 8)}`);
  }

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
      {!isDraft && closedMetaParts.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {closedMetaParts.join(" • ")}
        </p>
      )}
    </header>
  );
}

/**
 * Click-to-edit description line. Renders muted single-line text by default;
 * switches to a multi-line textarea on click. Saves on blur or Cmd/Ctrl+Enter;
 * Escape cancels. Read-only mode just renders the static line (no pencil).
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
    return (
      <div className="flex items-start gap-2">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              commit();
            }
          }}
          rows={2}
          disabled={mutation.isPending}
          placeholder="Describe what this campaign is for…"
          className="flex-1 resize-y rounded-md border bg-background px-2 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
        />
        <span className="text-[10px] text-muted-foreground pt-1.5 shrink-0">
          ⌘↵ to save · Esc to cancel
        </span>
      </div>
    );
  }

  const hasDescription = !!campaign.description?.trim();
  if (!hasDescription && !editable) return null;

  return (
    <div className="group flex items-start gap-2">
      <p
        className={`text-sm flex-1 ${
          hasDescription
            ? "text-muted-foreground"
            : "text-muted-foreground/60 italic"
        }`}
      >
        {hasDescription ? campaign.description : "Add a description…"}
      </p>
      {editable && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          aria-label="Edit description"
          className="opacity-0 group-hover:opacity-100 focus:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
