# `ListProtocolsByProject` has no role guard

**Found:** 2026-11-13, whole-branch review of `feat/curves-relabel-compare`.
**Status:** Open. Pre-existing, not introduced by that branch.

## Root cause

`ListProtocolsByProject.__call__` (`backend/src/cellar/application/screening/manage_protocol.py`,
around line 423) starts with `require_same_workspace(auth, input.workspace_id)` and no role
guard. The New Use Case Checklist in `docs/backend-code-guidelines.md` puts the role guard on
the first line of every `__call__`. Today any authenticated member of the workspace passes,
which matches a viewer guard in effect, but the rule is implicit and a later change to the
guards would miss this use case.

## Suggested fix

Add `require_viewer(auth)` as the first line, matching the other protocol list queries, and a
unit test asserting `AuthorizationError` for a caller without a workspace role.
