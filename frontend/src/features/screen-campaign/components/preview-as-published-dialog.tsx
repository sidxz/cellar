"use client";

/**
 * PreviewAsPublishedDialog (B6 bonus) — render a DRAFT through the DAIKON serializer.
 *
 * Fetches GET /api/v1/campaigns/{id}/preview-published and renders a summary
 * of the published JSON contract the screener will publish on close. 100%
 * reuses the backend's _serialize_* helpers; no new shape code here.
 */

import { Download, FileJson, Loader2 } from "lucide-react";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { saveText } from "@/shared/lib/api/download";
import { formatMeasurementValue } from "@/shared/lib/format-number";

import { usePreviewPublishedCampaignApiV1CampaignsCampaignIdPreviewPublishedGet } from "@/shared/lib/api/campaigns/campaigns";

interface PreviewAsPublishedDialogProps {
  campaignId: string;
  campaignName: string;
  open: boolean;
  onClose: () => void;
}

interface PublishedShape {
  campaign: {
    name: string;
    status: string;
    project?: { name: string } | null;
    closed_at?: string | null;
  };
  channels: { id: string; label: string }[];
  results: {
    molecule: { registration_number: string | null; name: string | null };
    decision: string;
    measurements: {
      channel_id: string;
      value: number | null;
      unit: string;
      hit_call: string | null;
    }[];
  }[];
  source_protocols: { name?: string; version?: number | null }[];
  published_collection: { name: string; size: number } | null;
}

export function PreviewAsPublishedDialog({
  campaignId,
  campaignName,
  open,
  onClose,
}: PreviewAsPublishedDialogProps) {
  const { data, isLoading } =
    usePreviewPublishedCampaignApiV1CampaignsCampaignIdPreviewPublishedGet(campaignId, undefined, {
      query: { enabled: open },
    });

  const doc = data as PublishedShape | undefined;

  function handleDownload() {
    if (!doc) return;
    saveText(
      JSON.stringify(doc, null, 2),
      `campaign-${campaignName.replace(/\s+/g, "-")}-preview.json`,
      "application/json",
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-4xl max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileJson className="h-5 w-5" />
            Preview as published
          </DialogTitle>
          <DialogDescription>
            This is the DAIKON-shaped document that will be exported when this campaign is closed.
            Reuses the same serializer used by the published endpoint.
          </DialogDescription>
        </DialogHeader>

        {isLoading || !doc ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <ScrollArea className="h-[60vh] pr-2">
            <div className="space-y-4">
              {/* Header */}
              <section className="space-y-1">
                <div className="text-xs uppercase text-muted-foreground">Campaign</div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold">{doc.campaign.name}</span>
                  <Badge variant="secondary">{doc.campaign.status}</Badge>
                  {doc.campaign.project?.name && (
                    <span className="text-xs text-muted-foreground">
                      {doc.campaign.project.name}
                    </span>
                  )}
                </div>
              </section>

              {/* Source protocols */}
              {doc.source_protocols?.length > 0 && (
                <section className="space-y-1">
                  <div className="text-xs uppercase text-muted-foreground">
                    Source protocols ({doc.source_protocols.length})
                  </div>
                  <ul className="text-sm space-y-0.5">
                    {doc.source_protocols.map((p, i) => (
                      <li key={i}>
                        {p.name}
                        {p.version != null && (
                          <span className="text-muted-foreground"> v{p.version}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Channels */}
              <section className="space-y-1">
                <div className="text-xs uppercase text-muted-foreground">
                  Channels ({doc.channels.length})
                </div>
                <div className="flex flex-wrap gap-1">
                  {doc.channels.map((c) => (
                    <Badge key={c.id} variant="outline">
                      {c.label}
                    </Badge>
                  ))}
                </div>
              </section>

              {/* Published collection */}
              {doc.published_collection && (
                <section className="space-y-1">
                  <div className="text-xs uppercase text-muted-foreground">
                    Published collection
                  </div>
                  <span className="text-sm">
                    {doc.published_collection.name}{" "}
                    <span className="text-muted-foreground">
                      ({doc.published_collection.size} molecules)
                    </span>
                  </span>
                </section>
              )}

              {/* Results table */}
              <section className="space-y-1">
                <div className="text-xs uppercase text-muted-foreground">
                  Results ({doc.results.length})
                </div>
                <div className="rounded border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left p-2">Compound</th>
                        <th className="text-left p-2">Decision</th>
                        {doc.channels.map((c) => (
                          <th key={c.id} className="text-left p-2">
                            {c.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {doc.results.slice(0, 50).map((r, i) => (
                        <tr key={i}>
                          <td className="p-2">
                            <div className="font-mono">{r.molecule.registration_number ?? "—"}</div>
                            {r.molecule.name && (
                              <div className="text-muted-foreground truncate max-w-[120px]">
                                {r.molecule.name}
                              </div>
                            )}
                          </td>
                          <td className="p-2">
                            <Badge variant="outline">{r.decision}</Badge>
                          </td>
                          {doc.channels.map((c) => {
                            const m = r.measurements.find((mm) => mm.channel_id === c.id);
                            if (!m || m.value == null) {
                              return (
                                <td key={c.id} className="p-2 text-muted-foreground">
                                  —
                                </td>
                              );
                            }
                            return (
                              <td key={c.id} className="p-2">
                                {formatMeasurementValue(m.value)} {m.unit !== "-" ? m.unit : ""}
                                {m.hit_call === "hit" && (
                                  <Badge className="ml-1 bg-orange-100 text-orange-800 text-[9px] px-1 py-0">
                                    HIT
                                  </Badge>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {doc.results.length > 50 && (
                    <p className="text-xs text-muted-foreground p-2 text-center">
                      Showing first 50 of {doc.results.length} results. Download JSON for full
                      content.
                    </p>
                  )}
                </div>
              </section>
            </div>
          </ScrollArea>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={handleDownload} disabled={!doc}>
            <Download className="mr-2 h-4 w-4" />
            Download JSON
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
