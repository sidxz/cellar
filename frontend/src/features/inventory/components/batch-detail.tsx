"use client";

import { ArrowLeft, Boxes } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { EntityLink } from "@/shared/components/entity-link";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useMolecule } from "@/features/chemical-registration/hooks/use-molecules";
import { useBatch } from "../hooks/use-batches";
import { SampleList } from "./sample-list";
import { BATCH_SOURCE_LABELS, type BatchSource } from "../types";

interface BatchDetailProps {
  batchId: string;
}

export function BatchDetail({ batchId }: BatchDetailProps) {
  const { data: batch, isLoading } = useBatch(batchId);
  const { data: molecule } = useMolecule(batch?.molecule_id);
  const { data: orgs } = useOrganizations();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Boxes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Batch not found</h3>
      </div>
    );
  }

  const supplier = orgs?.find((o) => o.id === batch.supplier_org_id);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link href="/inventory">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight font-mono">
              {batch.batch_number}
            </h1>
            <Badge variant="outline">
              {BATCH_SOURCE_LABELS[batch.source as BatchSource] ?? batch.source}
            </Badge>
          </div>
          {molecule && (
            <p className="mt-1 text-muted-foreground">
              Batch of{" "}
              <EntityLink
                type="compound"
                id={batch.molecule_id}
                label={`${molecule.registration_number} — ${molecule.name}`}
              />
            </p>
          )}
        </div>
      </div>

      {/* Properties */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Properties</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">Amount</p>
            <p className="font-medium">
              {batch.amount_value} {batch.amount_unit}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Purity</p>
            <p className="font-medium">
              {batch.purity != null ? `${batch.purity}%` : "\u2014"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Salt Form</p>
            <p className="font-medium">{batch.salt_form ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Appearance</p>
            <p className="font-medium">{batch.appearance ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Chemist</p>
            <p className="font-medium">{batch.chemist}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Synthesis Date</p>
            <p className="font-medium">{batch.synthesis_date ?? "\u2014"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Expiry Date</p>
            <p className="font-medium">{batch.expiry_date ?? "\u2014"}</p>
          </div>
          {supplier && (
            <div>
              <p className="text-xs text-muted-foreground">Supplier</p>
              <p className="font-medium">{supplier.name}</p>
            </div>
          )}
          {batch.vendor_catalog_number && (
            <div>
              <p className="text-xs text-muted-foreground">Catalog #</p>
              <p className="font-mono text-sm">{batch.vendor_catalog_number}</p>
            </div>
          )}
          {batch.vendor_lot_number && (
            <div>
              <p className="text-xs text-muted-foreground">Lot #</p>
              <p className="font-mono text-sm">{batch.vendor_lot_number}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Samples */}
      <div>
        <h2 className="text-lg font-semibold">Samples</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Physical samples derived from this batch.
        </p>
        <div className="mt-4">
          <SampleList batchId={batchId} />
        </div>
      </div>
    </div>
  );
}
