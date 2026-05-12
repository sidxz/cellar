"use client";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { Button } from "@/shared/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { useReportConfig, type CampaignReportConfig } from "../../lib/report-config";

interface CampaignReportSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
}

export function CampaignReportSheet({ open, onOpenChange, campaignId }: CampaignReportSheetProps) {
  const cfg = useReportConfig((s) => s.get(campaignId));
  const setCfg = useReportConfig((s) => s.set);
  const reset = useReportConfig((s) => s.reset);
  const patch = (p: Partial<CampaignReportConfig>) => setCfg(campaignId, p);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[420px]">
        <SheetHeader>
          <SheetTitle>Customize report</SheetTitle>
        </SheetHeader>
        <div className="space-y-6 py-6">
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Properties
            </h3>
            {(["mw", "logP", "hbd", "hba", "tpsa"] as const).map((k) => (
              <div key={k} className="flex items-center justify-between py-1">
                <Label className="capitalize">{k}</Label>
                <Switch
                  checked={cfg.showProperties[k]}
                  onCheckedChange={(v) =>
                    patch({ showProperties: { ...cfg.showProperties, [k]: v } })
                  }
                />
              </div>
            ))}
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Image size
            </h3>
            <RadioGroup
              value={cfg.imageSize}
              onValueChange={(v) => patch({ imageSize: v as CampaignReportConfig["imageSize"] })}
            >
              {(["small", "medium", "large"] as const).map((s) => (
                <div key={s} className="flex items-center gap-2">
                  <RadioGroupItem value={s} id={`size-${s}`} />
                  <Label htmlFor={`size-${s}`} className="capitalize">{s}</Label>
                </div>
              ))}
            </RadioGroup>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Columns
            </h3>
            <Row label="Decision reason" v={cfg.showDecisionReasonColumn} on={(v) => patch({ showDecisionReasonColumn: v })} />
            <Row label="Notes" v={cfg.showNotesColumn} on={(v) => patch({ showNotesColumn: v })} />
            <Row label="Override status" v={cfg.showOverrideStatusColumn} on={(v) => patch({ showOverrideStatusColumn: v })} />
          </section>
          <Button variant="ghost" size="sm" onClick={() => reset(campaignId)}>
            Reset to defaults
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Row({ label, v, on }: { label: string; v: boolean; on: (b: boolean) => void }) {
  return (
    <div className="flex items-center justify-between py-1">
      <Label>{label}</Label>
      <Switch checked={v} onCheckedChange={on} />
    </div>
  );
}
