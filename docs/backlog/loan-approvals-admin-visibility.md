# Loans UI hides verb buttons from workspace admins outside the owner org

**Status:** open · **Found:** 2026-08-13 (S4 Task 10 review) · **Origin:** MeResponse lacks an admin/role field

`require_loan_authority` gives workspace admins a full bypass (deliberate — no Sentinel
`cellar:approve_loan` grants exist yet, so admins may initially be the ONLY approvers for
orgs they don't belong to), but the Loans UI's `canApprove` is
`me.org_id === loan.owner_org_id` only, so a foreign-org admin sees no verb buttons.
Server-side authority is unaffected — this is a visibility gap, not an authorization one.

**Fix shape:** surface `workspace_role`/`is_admin` on `GET /api/v1/user/me` (backend
MeResponse + orval regen), then `canApprove = me.is_admin || me.org_id === loan.owner_org_id`
in `frontend/src/features/inventory/components/loan-card.tsx`. Intake: S5 polish batch.
