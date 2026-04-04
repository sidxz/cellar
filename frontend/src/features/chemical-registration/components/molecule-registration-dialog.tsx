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
import { Textarea } from "@/shared/components/ui/textarea";
import { Switch } from "@/shared/components/ui/switch";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { useRegisterMolecule } from "../hooks/use-molecules";
import { MOLECULE_TYPE_LABELS, type MoleculeType } from "../types";

interface MoleculeRegistrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MoleculeRegistrationDialog({
  open,
  onOpenChange,
}: MoleculeRegistrationDialogProps) {
  const { data: orgs } = useOrganizations();
  const registerMutation = useRegisterMolecule();

  const [name, setName] = useState("");
  const [smiles, setSmiles] = useState("");
  const [moleculeType, setMoleculeType] = useState<string>("small_molecule");
  const [orgId, setOrgId] = useState<string>("");
  const [isUndisclosed, setIsUndisclosed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setSmiles("");
    setMoleculeType("small_molecule");
    setOrgId("");
    setIsUndisclosed(false);
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!orgId) {
      setError("Organization is required");
      return;
    }
    if (!isUndisclosed && !smiles.trim()) {
      setError("SMILES is required for disclosed compounds");
      return;
    }

    try {
      await registerMutation.mutateAsync({
        name: name.trim(),
        smiles: isUndisclosed ? null : smiles.trim(),
        molecule_type: moleculeType,
        originating_org_id: orgId,
      });
      reset();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Registration failed";
      setError(message);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Register Compound</DialogTitle>
          <DialogDescription>
            Register a new chemical compound in the workspace.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="e.g. Aspirin"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="undisclosed"
              checked={isUndisclosed}
              onCheckedChange={setIsUndisclosed}
            />
            <Label htmlFor="undisclosed">Undisclosed (no structure)</Label>
          </div>

          {!isUndisclosed && (
            <div className="grid gap-2">
              <Label htmlFor="smiles">SMILES</Label>
              <Textarea
                id="smiles"
                placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
                value={smiles}
                onChange={(e) => setSmiles(e.target.value)}
                rows={2}
                className="font-mono text-sm"
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="type">Molecule Type</Label>
            <Select value={moleculeType} onValueChange={setMoleculeType}>
              <SelectTrigger id="type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(MOLECULE_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="org">Originating Organization</Label>
            <Select value={orgId} onValueChange={setOrgId}>
              <SelectTrigger id="org">
                <SelectValue placeholder="Select organization" />
              </SelectTrigger>
              <SelectContent>
                {orgs?.map((org) => (
                  <SelectItem key={org.id} value={org.id}>
                    {org.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={registerMutation.isPending}
          >
            {registerMutation.isPending ? "Registering..." : "Register"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
