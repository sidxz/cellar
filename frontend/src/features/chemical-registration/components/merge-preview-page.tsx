"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { useBreadcrumbTrail } from "@/shared/components/layout/breadcrumb-context";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, Loader2, ShieldAlert, X } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useConfirmDisclosure,
  useMergeImpact,
  useRejectDisclosure,
} from "../hooks/use-disclosures";
import { useDisclosuresForMolecule } from "../hooks/use-disclosures";
import { useMolecule } from "../hooks/use-molecules";
import { ImpactRow } from "./merge-impact-row";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MergePreviewPageProps {
  compoundId: string;
  disclosureId: string;
}

// ---------------------------------------------------------------------------
// MergePreviewPage
// ---------------------------------------------------------------------------

export function MergePreviewPage({ compoundId, disclosureId }: MergePreviewPageProps) {
  const router = useRouter();

  // Load the disclosure to get the matched_molecule_id
  const disclosuresQuery = useDisclosuresForMolecule(compoundId);
  const disclosure = disclosuresQuery.data?.find((d) => d.id === disclosureId);

  const sourceQuery = useMolecule(compoundId);
  const targetQuery = useMolecule(disclosure?.matched_molecule_id ?? undefined);
  const impactQuery = useMergeImpact(compoundId, disclosure?.matched_molecule_id ?? undefined);

  const confirmMutation = useConfirmDisclosure(disclosureId);
  const rejectMutation = useRejectDisclosure(disclosureId);

  const isLoading = disclosuresQuery.isLoading || sourceQuery.isLoading || targetQuery.isLoading;

  const source = sourceQuery.data;
  const target = targetQuery.data;
  const impact = impactQuery.data;

  const hasBlockers = (impact?.blockers?.length ?? 0) > 0;

  // Set human-readable breadcrumbs
  useBreadcrumbTrail([
    { label: "Compounds", href: "/compounds" },
    {
      label: source?.registration_number ?? "...",
      href: `/compounds/${compoundId}`,
    },
    { label: "Merge Preview" },
  ]);

  const handleConfirm = async () => {
    await confirmMutation.mutateAsync();
    router.push(`/compounds/${disclosure?.matched_molecule_id}`);
  };

  const handleReject = async () => {
    await rejectMutation.mutateAsync({});
    router.push(`/compounds/${compoundId}`);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Disclosure not found or not in pending_confirmation state
  if (!disclosure || disclosure.status !== "pending_confirmation") {
    return (
      <div className="mx-auto max-w-3xl space-y-4 py-8">
        <Button variant="ghost" size="sm" onClick={() => router.push(`/compounds/${compoundId}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to compound
        </Button>
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {!disclosure
              ? "Disclosure not found."
              : `Disclosure is in "${disclosure.status}" status — no confirmation needed.`}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 py-6">
      {/* Back button */}
      <Button variant="ghost" size="sm" onClick={() => router.push(`/compounds/${compoundId}`)}>
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to {source?.registration_number ?? "compound"}
      </Button>

      {/* Title */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Merge Preview</h1>
        <p className="text-muted-foreground">
          Structure match found during disclosure. Review the impact before confirming.
        </p>
      </div>

      {/* Side-by-side comparison */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Source card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              Source
              <Badge variant="outline" className="text-xs font-normal">
                will be absorbed
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="font-mono text-sm font-semibold">{source?.registration_number}</div>
            <div className="text-sm text-muted-foreground">{source?.name}</div>
            <Badge variant="outline" className="border-yellow-500/40 text-yellow-400">
              Undisclosed
            </Badge>
            {source?.identifiers && source.identifiers.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground">Identifiers</div>
                {source.identifiers.map((id) => (
                  <div key={id.id} className="text-xs text-muted-foreground">
                    {id.identifier_type}: {id.identifier}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Target card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              Target
              <Badge
                variant="outline"
                className="border-success/40 text-success text-xs font-normal"
              >
                survives
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="font-mono text-sm font-semibold">{target?.registration_number}</div>
            <div className="text-sm text-muted-foreground">{target?.name}</div>
            {target?.structure?.smiles && (
              <StructureThumbnail smiles={target.structure.smiles} size={160} />
            )}
            {target?.descriptors?.molecular_weight && (
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>MW: {target.descriptors.molecular_weight.toFixed(2)}</span>
                {target.descriptors.logp != null && (
                  <span>LogP: {target.descriptors.logp.toFixed(2)}</span>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Arrow between cards */}
      <div className="flex justify-center -my-2">
        <div className="flex items-center gap-2 rounded-full border bg-muted px-4 py-1.5 text-sm text-muted-foreground">
          <ArrowRight className="h-4 w-4" />
          Data will move from source to target
        </div>
      </div>

      {/* Impact sections */}
      {impactQuery.isLoading && (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading impact analysis...
          </CardContent>
        </Card>
      )}

      {impact && impact.categories.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Data That Will Move</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {impact.categories.map((cat) => (
              <ImpactRow key={cat.name} category={cat} />
            ))}
          </CardContent>
        </Card>
      )}

      {impact && impact.categories.length === 0 && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            No data associated with the source compound. Merge will only tombstone the source
            record.
          </CardContent>
        </Card>
      )}

      {/* Blockers */}
      {hasBlockers && (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
          <div className="space-y-1">
            <p className="text-sm font-medium text-destructive">Merge blocked</p>
            {impact?.blockers.map((b, i) => (
              <p key={i} className="text-sm text-destructive/80">
                {b}
              </p>
            ))}
          </div>
        </div>
      )}

      {!hasBlockers && impact && (
        <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/5 p-3 text-sm text-success">
          <Check className="h-4 w-4" />
          No blockers found — merge can proceed.
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 border-t pt-4">
        <Button
          variant="destructive"
          onClick={handleConfirm}
          disabled={
            hasBlockers ||
            impactQuery.isLoading ||
            confirmMutation.isPending ||
            rejectMutation.isPending
          }
        >
          {confirmMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Merging...
            </>
          ) : (
            <>
              <Check className="mr-2 h-4 w-4" />
              Confirm Merge
            </>
          )}
        </Button>
        <Button
          variant="outline"
          onClick={handleReject}
          disabled={confirmMutation.isPending || rejectMutation.isPending}
        >
          {rejectMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Rejecting...
            </>
          ) : (
            <>
              <X className="mr-2 h-4 w-4" />
              Reject
            </>
          )}
        </Button>

        <div className="ml-auto text-xs text-muted-foreground">
          <AlertTriangle className="mr-1 inline h-3 w-3" />
          Merging is irreversible. The source compound becomes a tombstone.
        </div>
      </div>
    </div>
  );
}
