"use client";

import { EmptyState } from "@/shared/components/empty-state";
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
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Building2,
  ChevronRight,
  DoorOpen,
  MapPin,
  Pencil,
  Plus,
  Refrigerator,
  Snowflake,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import {
  useDeleteStorageLocation,
  useStorageLocationsWithCounts,
  useUpdateStorageLocation,
} from "../hooks/use-storage-locations";
import type { StorageLocation, StorageLocationType, StorageLocationWithCount } from "../types";
import { CreateStorageLocationDialog } from "./create-storage-location-dialog";

const TYPE_ICONS: Partial<Record<StorageLocationType, React.ReactNode>> = {
  site: <MapPin className="h-4 w-4" />,
  building: <Building2 className="h-4 w-4" />,
  room: <DoorOpen className="h-4 w-4" />,
  freezer: <Snowflake className="h-4 w-4" />,
  refrigerator: <Refrigerator className="h-4 w-4" />,
};

function buildTree(locations: StorageLocationWithCount[]): StorageLocationWithCount[] {
  return locations.filter((loc) => loc.parent_id === null);
}

function getChildren(
  locations: StorageLocationWithCount[],
  parentId: string,
): StorageLocationWithCount[] {
  return locations.filter((loc) => loc.parent_id === parentId);
}

function LocationNode({
  location,
  allLocations,
  depth = 0,
}: {
  location: StorageLocationWithCount;
  allLocations: StorageLocationWithCount[];
  depth?: number;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const [editOpen, setEditOpen] = useState(false);
  const [addChildOpen, setAddChildOpen] = useState(false);
  const deleteMutation = useDeleteStorageLocation();
  const children = getChildren(allLocations, location.id);
  const hasChildren = children.length > 0;
  const icon = TYPE_ICONS[location.type] ?? <MapPin className="h-4 w-4" />;

  return (
    <div>
      <div
        className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        {hasChildren ? (
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={() => setExpanded(!expanded)}
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            />
          </Button>
        ) : (
          <div className="h-5 w-5" />
        )}
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-sm font-medium">{location.name}</span>
        <Badge variant="outline" className="ml-auto text-xs">
          {location.type}
        </Badge>
        {location.temperature && (
          <span className="text-xs text-muted-foreground">{location.temperature}</span>
        )}
        {location.rows != null && location.columns != null ? (
          <span className="text-xs text-muted-foreground">
            {location.sample_count}/{location.rows * location.columns}
          </span>
        ) : (
          location.sample_count > 0 && (
            <span className="text-xs text-muted-foreground">{location.sample_count} samples</span>
          )
        )}
        <div className="hidden gap-1 group-hover:flex">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            title="Add sub-location"
            onClick={() => setAddChildOpen(true)}
          >
            <Plus className="h-3 w-3" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditOpen(true)}>
            <Pencil className="h-3 w-3" />
          </Button>
          {!hasChildren && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground hover:text-destructive"
              onClick={() => deleteMutation.mutate(location.id)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
      {expanded &&
        children.map((child) => (
          <LocationNode
            key={child.id}
            location={child}
            allLocations={allLocations}
            depth={depth + 1}
          />
        ))}
      <EditStorageLocationDialog location={location} open={editOpen} onOpenChange={setEditOpen} />
      <CreateStorageLocationDialog
        open={addChildOpen}
        onOpenChange={setAddChildOpen}
        defaultParentId={location.id}
      />
    </div>
  );
}

function EditStorageLocationDialog({
  location,
  open,
  onOpenChange,
}: {
  location: StorageLocation;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdateStorageLocation(location.id);
  const [name, setName] = useState(location.name);
  const [barcode, setBarcode] = useState(location.barcode ?? "");
  const [temperature, setTemperature] = useState(location.temperature ?? "");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="">
        <DialogHeader>
          <DialogTitle>Edit Location</DialogTitle>
          <DialogDescription>
            Update {location.name} ({location.type}).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Barcode</Label>
            <Input
              placeholder="Optional barcode"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label>Temperature</Label>
            <Input
              placeholder="e.g. -20°C"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            onClick={() => {
              mutation.mutate(
                {
                  name: name || null,
                  barcode: barcode || null,
                  temperature: temperature || null,
                },
                { onSuccess: () => onOpenChange(false) },
              );
            }}
            disabled={!name.trim() || mutation.isPending}
          >
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function StorageBrowser() {
  const { data: locations, isLoading } = useStorageLocationsWithCounts();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (!locations?.length) {
    return (
      <EmptyState
        icon={MapPin}
        title="No storage locations"
        description="Configure storage locations to track where samples are stored."
      />
    );
  }

  const roots = buildTree(locations);

  return (
    <div className="rounded-lg border p-2">
      {roots.map((root) => (
        <LocationNode key={root.id} location={root} allLocations={locations} />
      ))}
    </div>
  );
}
