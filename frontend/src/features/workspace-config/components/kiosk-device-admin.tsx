"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { formatDate } from "@/shared/lib/format-date";
import { showSuccess } from "@/shared/lib/toast";
import { zodResolver } from "@hookform/resolvers/zod";
import { Copy, Plus, ScanLine } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import {
  type CreateKioskDeviceInput,
  type CreatedKioskDevice,
  type KioskDevice,
  useCreateKioskDevice,
  useKioskDevices,
  useRevokeKioskDevice,
} from "../hooks/use-kiosk-devices";

// ---------------------------------------------------------------------------
// Add-device dialog
// ---------------------------------------------------------------------------

const formSchema = z.object({
  name: z.string().min(1, "Name is required").max(100),
  org_id: z.string().min(1, "Organization is required"),
});

type FormValues = z.infer<typeof formSchema>;

const defaultValues: FormValues = { name: "", org_id: "" };

interface CreateDeviceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: CreatedKioskDevice) => void;
}

function CreateDeviceDialog({ open, onOpenChange, onCreated }: CreateDeviceDialogProps) {
  const { data: orgs } = useOrgs();
  const create = useCreateKioskDevice();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    if (open) form.reset(defaultValues);
  }, [open, form]);

  const onSubmit = async (values: FormValues) => {
    const created = await create.mutateAsync(values as CreateKioskDeviceInput);
    onOpenChange(false);
    onCreated(created);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Kiosk Device</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="device-name">Name</Label>
              <Input
                id="device-name"
                {...form.register("name")}
                placeholder="e.g., Bench 3 scanner"
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Organization</Label>
              <Controller
                name="org_id"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
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
                )}
              />
              {form.formState.errors.org_id && (
                <p className="text-xs text-destructive">{form.formState.errors.org_id.message}</p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting || create.isPending}>
              {create.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Token-reveal dialog — shown exactly once, immediately after create
// ---------------------------------------------------------------------------

interface TokenRevealDialogProps {
  issued: CreatedKioskDevice | null;
  onClose: () => void;
}

function TokenRevealDialog({ issued, onClose }: TokenRevealDialogProps) {
  return (
    <Dialog
      open={issued !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Device token for &ldquo;{issued?.name}&rdquo;</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          This token is shown only once — store it in the scanner now. Revoke the device to
          invalidate it.
        </p>
        <div className="flex items-center gap-2">
          <code
            className="flex-1 overflow-x-auto rounded-md border bg-muted px-3 py-2 font-mono text-sm"
            data-testid="kiosk-token"
          >
            {issued?.token}
          </code>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              if (issued) {
                await navigator.clipboard.writeText(issued.token);
                showSuccess("Token copied");
              }
            }}
          >
            <Copy className="mr-2 h-4 w-4" />
            Copy
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Revoke confirmation dialog
// ---------------------------------------------------------------------------

interface RevokeDialogProps {
  device: KioskDevice | null;
  onOpenChange: (open: boolean) => void;
}

function RevokeDialog({ device, onOpenChange }: RevokeDialogProps) {
  const revoke = useRevokeKioskDevice();

  const handleConfirm = async () => {
    if (!device) return;
    await revoke.mutateAsync({ deviceId: device.id });
    onOpenChange(false);
  };

  return (
    <Dialog open={device !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Revoke device?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Revoke <span className="font-medium text-foreground">{device?.name}</span>? Its token will
          no longer be accepted by the kiosk scanner. This action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={revoke.isPending}>
            {revoke.isPending ? "Revoking..." : "Revoke"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Device table
// ---------------------------------------------------------------------------

interface KioskDeviceTableProps {
  devices: KioskDevice[];
  orgName: (id: string) => string;
  onRevoke: (device: KioskDevice) => void;
}

function KioskDeviceTable({ devices, orgName, onRevoke }: KioskDeviceTableProps) {
  if (devices.length === 0) {
    return <EmptyState variant="inline" icon={ScanLine} title="No kiosk devices registered yet." />;
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Organization</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last seen</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {devices.map((d) => (
            <TableRow key={d.id}>
              <TableCell className="font-medium">{d.name}</TableCell>
              <TableCell>{orgName(d.org_id)}</TableCell>
              <TableCell>
                <Badge variant={d.is_active ? "secondary" : "outline"}>
                  {d.is_active ? "Active" : "Revoked"}
                </Badge>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {d.last_seen_at ? formatDate(d.last_seen_at) : "Never"}
              </TableCell>
              <TableCell>
                {d.is_active && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => onRevoke(d)}
                  >
                    Revoke
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KioskDeviceAdmin — main component
// ---------------------------------------------------------------------------

export function KioskDeviceAdmin() {
  const [createOpen, setCreateOpen] = useState(false);
  const [issued, setIssued] = useState<CreatedKioskDevice | null>(null);
  const [revoking, setRevoking] = useState<KioskDevice | null>(null);

  const { data: devices, isLoading } = useKioskDevices();
  const { data: orgs } = useOrgs();

  const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? "Unknown org";

  return (
    <>
      <PageHeader
        title="Kiosk Devices"
        subtitle="Manage barcode scanners authorized to check plates in and out."
      >
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Device
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <SkeletonList />
        ) : (
          <KioskDeviceTable devices={devices ?? []} orgName={orgName} onRevoke={setRevoking} />
        )}
      </div>

      <CreateDeviceDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={setIssued} />

      <TokenRevealDialog issued={issued} onClose={() => setIssued(null)} />

      <RevokeDialog device={revoking} onOpenChange={(open) => !open && setRevoking(null)} />
    </>
  );
}
