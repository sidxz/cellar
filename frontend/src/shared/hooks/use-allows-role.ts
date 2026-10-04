import { type WorkspaceRole, useAuthzHasRole } from "@duar-auth/nextjs";

/** `allows(role)`: does the signed-in user hold at least `role`? One predicate
 * for checking several roles (a hook can't run per nav entry), with the same
 * hierarchy as `useAuthzHasRole`. */
export function useAllowsRole(): (role: WorkspaceRole) => boolean {
  const atLeast: Record<WorkspaceRole, boolean> = {
    viewer: useAuthzHasRole("viewer"),
    editor: useAuthzHasRole("editor"),
    admin: useAuthzHasRole("admin"),
    owner: useAuthzHasRole("owner"),
  };
  return (role) => atLeast[role];
}
