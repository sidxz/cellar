"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import type { PlateData } from "@/shared/lib/api/model";
import Link from "next/link";
import { useState } from "react";
import { useLinkRunPlate, useUnlinkRunPlate } from "../hooks/use-plate-setup";

interface RunPlateLinkProps {
  runId: string;
  plate: PlateData;
  /** Locked run or a viewer: show the link, hide the link/unlink controls. */
  readOnly?: boolean;
}

/** Physical-plate link for one run plate: barcode → inventory plate page,
 *  plus link/unlink by barcode or plate label. Errors toast globally. */
export function RunPlateLink({ runId, plate, readOnly }: RunPlateLinkProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const link = useLinkRunPlate(runId);
  const unlink = useUnlinkRunPlate(runId);

  if (plate.registered_plate_id) {
    return (
      <span className="inline-flex items-center gap-2 text-xs">
        <Link
          href={`/inventory/plates/${plate.registered_plate_id}`}
          className="font-mono text-primary hover:underline"
          title={plate.registered_plate_label ?? undefined}
        >
          {plate.registered_plate_barcode}
        </Link>
        {plate.registered_plate_label ? (
          <span className="text-muted-foreground">{plate.registered_plate_label}</span>
        ) : null}
        {readOnly ? null : (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-2 text-xs"
            disabled={unlink.isPending}
            onClick={() => unlink.mutate({ plateId: plate.plate_id })}
          >
            Unlink
          </Button>
        )}
      </span>
    );
  }

  if (readOnly) return null;

  const submit = () =>
    link.mutate(
      { plateId: plate.plate_id, barcode: value.trim() },
      {
        onSuccess: () => {
          setOpen(false);
          setValue("");
        },
      },
    );

  return (
    <>
      <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setOpen(true)}>
        Link plate
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Link physical plate</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="link-plate-ref">Barcode or plate name</Label>
            <Input
              id="link-plate-ref"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && value.trim()) submit();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!value.trim() || link.isPending} onClick={submit}>
              Link
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
