"use client";

import { useState } from "react";
import { Building2, Plus } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useOrganizations } from "../hooks/use-organizations";
import { ORG_TYPE_LABELS, type Organization } from "../types";
import { OrganizationDialog } from "./organization-dialog";

export function OrganizationList() {
  const { data: orgs, isLoading } = useOrganizations(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Organization | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Organizations"
        subtitle="Manage partner organizations, CROs, and vendors."
      >
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Organization
        </Button>
      </PageHeader>

      {orgs && orgs.length > 0 ? (
        <div className="mt-6 rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[100px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {orgs.map((org) => (
                <TableRow key={org.id}>
                  <TableCell className="font-medium">{org.name}</TableCell>
                  <TableCell>{ORG_TYPE_LABELS[org.org_type]}</TableCell>
                  <TableCell>
                    {org.contact_name && (
                      <span className="text-sm">{org.contact_name}</span>
                    )}
                    {org.contact_email && (
                      <span className="block text-xs text-muted-foreground">
                        {org.contact_email}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={org.is_active ? "default" : "secondary"}>
                      {org.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditing(org);
                        setDialogOpen(true);
                      }}
                    >
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
          <Building2 className="h-10 w-10" />
          <p>No organizations yet.</p>
        </div>
      )}

      <OrganizationDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        organization={editing}
      />
    </>
  );
}
