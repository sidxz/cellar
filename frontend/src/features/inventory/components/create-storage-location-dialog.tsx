"use client";

import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  useCreateStorageLocation,
  useStorageLocations,
} from "../hooks/use-storage-locations";
import type { StorageLocation } from "../types";

interface CreateStorageLocationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultParentId?: string;
}

const LOCATION_TYPES = [
  { value: "site", label: "Site" },
  { value: "building", label: "Building" },
  { value: "room", label: "Room" },
  { value: "freezer", label: "Freezer" },
  { value: "refrigerator", label: "Refrigerator" },
  { value: "shelf", label: "Shelf" },
  { value: "rack", label: "Rack" },
  { value: "box", label: "Box" },
  { value: "drawer", label: "Drawer" },
];

export function CreateStorageLocationDialog({
  open,
  onOpenChange,
  defaultParentId,
}: CreateStorageLocationDialogProps) {
  const createMutation = useCreateStorageLocation();
  const { data: locations } = useStorageLocations();
  const [name, setName] = useState("");
  const [type, setType] = useState(defaultParentId ? "shelf" : "site");
  const [parentId, setParentId] = useState<string>(defaultParentId ?? "");
  const [temperature, setTemperature] = useState("");
  const [barcode, setBarcode] = useState("");

  const handleSubmit = () => {
    createMutation.mutate(
      {
        name,
        type,
        parent_id: parentId || null,
        temperature: temperature || null,
        barcode: barcode || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setName("");
          setType("site");
          setParentId("");
          setTemperature("");
          setBarcode("");
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Storage Location</DialogTitle>
          <DialogDescription>
            Add a new location to your storage hierarchy.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              placeholder="e.g., Freezer A, Room 101"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Type</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LOCATION_TYPES.map((lt) => (
                  <SelectItem key={lt.value} value={lt.value}>
                    {lt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {type !== "site" && (
            <div className="grid gap-2">
              <Label>Parent Location</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={parentId}
                onChange={(e) => setParentId(e.target.value)}
              >
                <option value="">Select parent...</option>
                {locations?.map((loc: StorageLocation) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name} ({loc.type})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="grid gap-2">
            <Label>Temperature</Label>
            <Input
              placeholder="e.g., -80C, -20C, 4C, RT"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Barcode</Label>
            <Input
              placeholder="Optional barcode"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!name || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Location"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
