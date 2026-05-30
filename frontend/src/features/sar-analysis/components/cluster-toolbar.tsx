"use client";

import { ReactNode } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Slider } from "@/shared/components/ui/slider";
import type { UmapPicker } from "@/features/sar-analysis/types";

interface ClusterToolbarProps {
  picker: UmapPicker;
  n: number;
  threshold: number;
  onPickerChange: (p: UmapPicker) => void;
  onNChange: (n: number) => void;
  onThresholdChange: (t: number) => void;
  onDiversify: () => void;
  /** True when toolbar values diverge from the last committed compute — surfaces
   *  the Diversify button as the explicit recompute trigger. */
  diversifyDirty?: boolean;
  colorPicker: ReactNode;
}

export function ClusterToolbar(props: ClusterToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-b px-3 py-2">
      {props.colorPicker}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Picker:</span>
        <Select
          value={props.picker}
          onValueChange={(v) => props.onPickerChange(v as UmapPicker)}
        >
          <SelectTrigger className="h-8 w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="maxmin">MaxMin</SelectItem>
            <SelectItem value="butina">Butina</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {props.picker === "maxmin" && (
        <div className="flex items-center gap-2 text-xs">
          <Label htmlFor="cluster-n">N</Label>
          <Input
            id="cluster-n"
            type="number"
            min={1}
            max={1000}
            value={props.n}
            onChange={(e) => props.onNChange(Number(e.target.value))}
            className="h-8 w-20"
          />
        </div>
      )}

      <div className="flex items-center gap-2 text-xs">
        <Label>
          {props.picker === "butina" ? "Threshold" : "Cluster threshold"}
        </Label>
        <div className="w-40">
          <Slider
            aria-label={
              props.picker === "butina" ? "Threshold" : "Cluster threshold"
            }
            min={0.05}
            max={0.95}
            step={0.05}
            value={[props.threshold]}
            onValueChange={(v) => props.onThresholdChange(v[0])}
          />
        </div>
        <span className="font-mono text-xs">{props.threshold.toFixed(2)}</span>
      </div>

      <Button
        size="sm"
        variant={props.diversifyDirty ? "default" : "outline"}
        onClick={props.onDiversify}
      >
        {props.diversifyDirty ? "Apply changes" : "Diversify"}
      </Button>
    </div>
  );
}
