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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Switch } from "@/shared/components/ui/switch";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useEffect, useState } from "react";
import { useOrgPlatePolicy, useSetOrgPlatePolicy } from "../hooks/use-org-plate-policy";

const CONFIRMATION_OPTIONS = [
  { value: "kiosk_scan", label: "Kiosk scan" },
  { value: "admin_confirm", label: "Admin confirm" },
  { value: "none", label: "None" },
] as const;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Admin dialog to view/edit a single org's plate loan & visibility policy. */
export function OrgPlatePolicyDialog({ open, onOpenChange }: Props) {
  const { data: orgs } = useOrgs();
  const [orgId, setOrgId] = useState("");
  const { data: policy, isLoading } = useOrgPlatePolicy(orgId || undefined);
  const setPolicy = useSetOrgPlatePolicy(orgId);

  const [requireApproval, setRequireApproval] = useState(false);
  const [confirmation, setConfirmation] = useState<string>("kiosk_scan");
  const [dueDays, setDueDays] = useState("");
  const [platesPrivate, setPlatesPrivate] = useState(false);

  // Reset the picker each time the dialog is reopened.
  useEffect(() => {
    if (!open) setOrgId("");
  }, [open]);

  // Reset fields synchronously with the org change, so a Save racing the new
  // org's policy fetch can never write the previous org's values onto it.
  const handleOrgChange = (id: string) => {
    setOrgId(id);
    setRequireApproval(false);
    setConfirmation("kiosk_scan");
    setDueDays("");
    setPlatesPrivate(false);
  };

  // Prefill the form whenever the selected org's policy loads.
  useEffect(() => {
    if (policy) {
      setRequireApproval(policy.require_approval);
      setConfirmation(policy.confirmation);
      setDueDays(policy.default_due_days != null ? String(policy.default_due_days) : "");
      setPlatesPrivate(policy.plates_private);
    }
  }, [policy]);

  const handleSave = () => {
    if (!orgId) return;
    setPolicy.mutate(
      {
        require_approval: requireApproval,
        confirmation: confirmation as (typeof CONFIRMATION_OPTIONS)[number]["value"],
        default_due_days: dueDays.trim() ? Number(dueDays) : null,
        plates_private: platesPrivate,
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Org Plate Policy</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="policy-org">Organization</Label>
            <Select value={orgId} onValueChange={handleOrgChange}>
              <SelectTrigger id="policy-org">
                <SelectValue placeholder="Select organization..." />
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

          {orgId && !isLoading && (
            <>
              <div className="flex items-center gap-2">
                <Switch
                  id="policy-require-approval"
                  checked={requireApproval}
                  onCheckedChange={setRequireApproval}
                />
                <Label htmlFor="policy-require-approval">Require approval for plate loans</Label>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="policy-confirmation">Loan confirmation</Label>
                <Select value={confirmation} onValueChange={setConfirmation}>
                  <SelectTrigger id="policy-confirmation">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CONFIRMATION_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="policy-due-days">Default due days</Label>
                <Input
                  id="policy-due-days"
                  type="number"
                  min={1}
                  value={dueDays}
                  onChange={(e) => setDueDays(e.target.value)}
                  placeholder="No default"
                />
              </div>

              <div className="flex items-center gap-2">
                <Switch
                  id="policy-plates-private"
                  checked={platesPrivate}
                  onCheckedChange={setPlatesPrivate}
                />
                <Label htmlFor="policy-plates-private">Plates private to org</Label>
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!orgId || isLoading || setPolicy.isPending}>
            {setPolicy.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
