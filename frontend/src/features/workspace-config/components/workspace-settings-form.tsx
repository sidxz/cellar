"use client";

import { useEffect, useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Card } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  useUpdateWorkspaceSettings,
  useWorkspaceSettings,
} from "../hooks/use-workspace-settings";

export function WorkspaceSettingsForm() {
  const { data: settings, isLoading } = useWorkspaceSettings();
  const update = useUpdateWorkspaceSettings();

  const [defaultMolType, setDefaultMolType] = useState("");
  const [retentionDays, setRetentionDays] = useState("");
  const [sigRequired, setSigRequired] = useState("");

  useEffect(() => {
    if (settings) {
      setDefaultMolType(settings.default_molecule_type ?? "");
      setRetentionDays(settings.audit_retention_days?.toString() ?? "");
      setSigRequired(settings.signature_required_for.join(", "));
    }
  }, [settings]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const handleSave = async () => {
    await update.mutateAsync({
      default_molecule_type: defaultMolType || null,
      audit_retention_days: retentionDays ? parseInt(retentionDays, 10) : null,
      signature_required_for: sigRequired
        ? sigRequired.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
    });
  };

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight">Workspace Settings</h1>
      <p className="mt-1 text-muted-foreground">
        Configure registration rules, audit policies, and workspace-level defaults.
      </p>

      <Card className="mt-6 p-6">
        <div className="grid gap-6 max-w-lg">
          <div className="grid gap-2">
            <Label htmlFor="mol-type">Default Molecule Type</Label>
            <Input
              id="mol-type"
              value={defaultMolType}
              onChange={(e) => setDefaultMolType(e.target.value)}
              placeholder="e.g., small_molecule"
            />
            <p className="text-xs text-muted-foreground">
              Default molecule type for new registrations.
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="retention">Audit Retention (days)</Label>
            <Input
              id="retention"
              type="number"
              value={retentionDays}
              onChange={(e) => setRetentionDays(e.target.value)}
              placeholder="Unlimited"
            />
            <p className="text-xs text-muted-foreground">
              Leave empty for unlimited retention.
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="sig-required">Signature Required For</Label>
            <Input
              id="sig-required"
              value={sigRequired}
              onChange={(e) => setSigRequired(e.target.value)}
              placeholder="e.g., registration, disclosure"
            />
            <p className="text-xs text-muted-foreground">
              Comma-separated operation types requiring electronic signature.
            </p>
          </div>

          <div className="flex justify-end">
            <Button onClick={handleSave} disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save Settings"}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
