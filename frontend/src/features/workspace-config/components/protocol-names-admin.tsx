"use client";

import {
  useNameFlags,
  useRederiveNames,
} from "@/features/screening-assay/hooks/use-protocol-names-admin";
import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import type { NamingChangePreviewResponse } from "@/shared/lib/api/model";
import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { NamingChangePreview } from "./naming-change-preview";

const FLAG_LABEL: Record<string, string> = {
  needs_facts: "missing a field",
  needs_discriminator: "needs discriminator",
  name_conflict: "name conflict",
};

/** Admin: protocols whose name needs attention, and a check of every name against its facts. */
export function ProtocolNamesAdmin() {
  const { data: flags, isLoading } = useNameFlags();
  const rederive = useRederiveNames();
  const [preview, setPreview] = useState<NamingChangePreviewResponse | undefined>();
  const [open, setOpen] = useState(false);

  const check = () =>
    rederive.mutate(
      { dry_run: true, reason: "Names generated from fields" },
      {
        onSuccess: (result) => {
          setPreview({
            changes: result.changes.filter((c) => c.before !== c.after),
            collisions: [],
          });
          setOpen(true);
        },
      },
    );

  const apply = () =>
    rederive.mutate(
      { dry_run: false, reason: "Names generated from fields" },
      { onSuccess: () => setOpen(false) },
    );

  if (isLoading) return <SkeletonList />;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Protocol Names"
        subtitle="Names are generated from each protocol's category and fields."
      >
        <Button variant="outline" onClick={check} disabled={rederive.isPending}>
          Check all names
        </Button>
      </PageHeader>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Needs attention</h2>
        {flags && flags.length > 0 ? (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-32">Code</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead className="w-48">Why</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flags.map((f) => (
                  <TableRow key={f.protocol_id}>
                    <TableCell className="font-mono text-xs">{f.code}</TableCell>
                    <TableCell>
                      <Link href={`/assays/protocols/${f.protocol_id}`} className="hover:underline">
                        {f.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant="warning">{FLAG_LABEL[f.flag] ?? f.flag}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <EmptyState
            variant="inline"
            icon={CheckCircle2}
            title="Nothing needs attention"
            description="Every protocol name is complete and unique."
          />
        )}
      </section>

      <NamingChangePreview
        open={open}
        onOpenChange={setOpen}
        preview={preview}
        isLoading={rederive.isPending && !preview}
        onApply={apply}
        isApplying={rederive.isPending}
      />
    </div>
  );
}
