"use client";

import { useState } from "react";
import {
  MapPin,
  Building2,
  DoorOpen,
  Snowflake,
  Refrigerator,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useStorageLocations } from "../hooks/use-storage-locations";
import type { StorageLocation, StorageLocationType } from "../types";

const TYPE_ICONS: Partial<Record<StorageLocationType, React.ReactNode>> = {
  site: <MapPin className="h-4 w-4" />,
  building: <Building2 className="h-4 w-4" />,
  room: <DoorOpen className="h-4 w-4" />,
  freezer: <Snowflake className="h-4 w-4" />,
  refrigerator: <Refrigerator className="h-4 w-4" />,
};

function buildTree(locations: StorageLocation[]): StorageLocation[] {
  return locations.filter((loc) => loc.parent_id === null);
}

function getChildren(
  locations: StorageLocation[],
  parentId: string
): StorageLocation[] {
  return locations.filter((loc) => loc.parent_id === parentId);
}

function LocationNode({
  location,
  allLocations,
  depth = 0,
}: {
  location: StorageLocation;
  allLocations: StorageLocation[];
  depth?: number;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const children = getChildren(allLocations, location.id);
  const hasChildren = children.length > 0;
  const icon = TYPE_ICONS[location.type] ?? <MapPin className="h-4 w-4" />;

  return (
    <div>
      <div
        className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
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
          <span className="text-xs text-muted-foreground">
            {location.temperature}
          </span>
        )}
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
    </div>
  );
}

export function StorageBrowser() {
  const { data: locations, isLoading } = useStorageLocations();

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
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <MapPin className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No storage locations</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure storage locations to track where samples are stored.
        </p>
      </div>
    );
  }

  const roots = buildTree(locations);

  return (
    <div className="rounded-lg border p-2">
      {roots.map((root) => (
        <LocationNode
          key={root.id}
          location={root}
          allLocations={locations}
        />
      ))}
    </div>
  );
}
