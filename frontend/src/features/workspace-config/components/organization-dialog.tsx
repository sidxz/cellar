"use client";

import { useEffect, useState } from "react";
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
import {
  useCreateOrganization,
  useUpdateOrganization,
} from "../hooks/use-organizations";
import { ORG_TYPE_LABELS, type Organization, type OrganizationType } from "../types";

const ORG_TYPES = Object.entries(ORG_TYPE_LABELS) as [OrganizationType, string][];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organization: Organization | null;
}

export function OrganizationDialog({ open, onOpenChange, organization }: Props) {
  const [name, setName] = useState("");
  const [orgType, setOrgType] = useState<OrganizationType>("internal");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [isActive, setIsActive] = useState(true);

  const create = useCreateOrganization();
  const update = useUpdateOrganization(organization?.id ?? "");
  const isEdit = organization !== null;

  useEffect(() => {
    if (organization) {
      setName(organization.name);
      setOrgType(organization.org_type);
      setContactName(organization.contact_name ?? "");
      setContactEmail(organization.contact_email ?? "");
      setNotes(organization.notes ?? "");
      setIsActive(organization.is_active);
    } else {
      setName("");
      setOrgType("internal");
      setContactName("");
      setContactEmail("");
      setNotes("");
      setIsActive(true);
    }
  }, [organization, open]);

  const handleSubmit = async () => {
    const data = {
      name,
      org_type: orgType,
      contact_name: contactName || null,
      contact_email: contactEmail || null,
      notes: notes || null,
    };
    if (isEdit) {
      await update.mutateAsync({ ...data, is_active: isActive });
    } else {
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Organization" : "New Organization"}
          </DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="org-name">Name</Label>
            <Input
              id="org-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Eurofins Munich"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="org-type">Type</Label>
            <Select value={orgType} onValueChange={(v) => setOrgType(v as OrganizationType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ORG_TYPES.map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="contact-name">Contact Name</Label>
            <Input
              id="contact-name"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="contact-email">Contact Email</Label>
            <Input
              id="contact-email"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="notes">Notes</Label>
            <Input
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {isEdit && (
            <div className="flex items-center gap-2">
              <Switch
                id="is-active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
              <Label htmlFor="is-active">Active</Label>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!name.trim() || create.isPending || update.isPending}
          >
            {create.isPending || update.isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
