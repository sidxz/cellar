"use client";

import { MemberName } from "@/shared/components/entity-name";
import { MemberSelector } from "@/shared/components/member-selector";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/components/ui/dialog";
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
import { Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import {
  useAddProjectMember,
  useProjectMembers,
  useRemoveProjectMember,
  useUpdateMemberRole,
} from "../hooks/use-project-members";
import type { ProjectRole } from "../types";

interface ProjectMembersProps {
  projectId: string;
}

export function ProjectMembers({ projectId }: ProjectMembersProps) {
  const { data: members, isLoading } = useProjectMembers(projectId);
  const addMember = useAddProjectMember(projectId);
  const updateRole = useUpdateMemberRole(projectId);
  const removeMember = useRemoveProjectMember(projectId);

  const [addOpen, setAddOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [newRole, setNewRole] = useState<ProjectRole>("viewer");

  const handleAdd = () => {
    if (!selectedUserId) return;
    addMember.mutate(
      { user_id: selectedUserId, role: newRole },
      {
        onSuccess: () => {
          setAddOpen(false);
          setSelectedUserId(null);
          setNewRole("viewer");
        },
      },
    );
  };

  if (isLoading) return <div className="text-muted-foreground">Loading members...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Members</h3>
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="outline">
              <UserPlus className="mr-2 h-4 w-4" /> Add Member
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Project Member</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Member</Label>
                <MemberSelector
                  selectedId={selectedUserId}
                  onSelect={setSelectedUserId}
                  placeholder="Search by name or email..."
                />
              </div>
              <div>
                <Label>Role</Label>
                <Select value={newRole} onValueChange={(v) => setNewRole(v as ProjectRole)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                    <SelectItem value="manager">Manager</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={handleAdd} disabled={!selectedUserId || addMember.isPending}>
                Add
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead>Role</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {members?.map((m) => (
            <TableRow key={m.user_id}>
              <TableCell>
                <MemberName id={m.user_id} />
              </TableCell>
              <TableCell>
                <Select
                  value={m.role}
                  onValueChange={(role) => updateRole.mutate({ userId: m.user_id, role })}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                    <SelectItem value="manager">Manager</SelectItem>
                  </SelectContent>
                </Select>
              </TableCell>
              <TableCell>
                <Button size="icon" variant="ghost" onClick={() => removeMember.mutate(m.user_id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {members?.length === 0 && (
            <TableRow>
              <TableCell colSpan={3} className="text-muted-foreground text-center">
                No members yet
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
