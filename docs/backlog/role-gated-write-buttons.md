# Write buttons show for roles that can't use them

**Found:** 2026-10-04, while hiding admin pages from viewers (branch `feat/role-gated-admin-nav`). This is step 2 of that plan, tracked in sidxz/cellar#93. Step 1 (admin menu and pages, CDD Force Stop, `d1b4ea5d`) and step 3 (loan verbs, `9d3d573c`) are done.

**Root cause:** the frontend rarely checks the role before showing a write action, while the backend refuses most writes below editor (about 135 use cases need editor, about 25 need admin). A viewer sees Register Compound, New Project, imports and similar buttons, and gets a 403 on pressing one. About 177 hand-written write calls sit in the feature folders (inventory 71, screening-assay 48, chemical-registration 30, research-organization 16, workspace-config 5, sar-analysis 3, tagging 2, attachment 2), and only 22 components check a role.

Viewers can still add favorites, run exports and run SAR analyses, so those buttons stay.

**Fix direction:** go feature by feature. For each button that triggers a write, find its backend guard (`require_editor`, `require_admin`, `require_project_role`) and hide it below that role with `useAuthzHasRole`, or `useAllowsRole` when checking several roles. Project-scoped writes need the user's project role from the API, not just the workspace role. Add one test per feature that renders as a viewer and asserts the buttons are gone.
