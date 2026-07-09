# Phase 8 Trial Permission Boundary

## Business Loop

This phase stabilizes trial-run role permissions and menu exposure for normal operators.

The affected loop is:

Trial user login -> role menu exposure -> visible route access -> direct URL access -> high-risk action denial -> role permission matrix reconciliation.

## Scope

Included:

- Existing pilot trial roles and users.
- Existing `pilot_role_permissions` configuration data.
- Existing finance menu parent label compatibility.
- Existing role permission matrix, trial menu, visible navigation, direct access, and high-risk role audits.

Excluded:

- New users, roles, routes, menus, database tables, or columns.
- New permission model behavior.
- Changes to protected audit scripts.
- Changes to business document approval, posting, settlement, or period-close rules.

## Stabilization Finding

The finance trial role had correct runtime access boundaries, but its stored `action_permissions` still contained cross-group feature keys from sales, purchase, inventory, master data, and other modules. The role permission matrix audit treated those stored keys as extra access, even though direct access checks were already blocking the routes.

The finance menu parent label had also moved to `Finance Management` terminology while the trial menu audit still required the legacy finance/cost wording.

## Remediation

- The finance menu parent now includes both the product-facing finance management wording and the legacy finance/cost label required by trial audits.
- The finance row in `pilot_role_permissions` was reset to `default_actions_for_role("finance")`, keeping the role in the finance permission group only.

## Acceptance Checks

The loop is accepted when:

- Role permission matrix audit reports zero findings.
- Trial user menu audit passes.
- Trial visible navigation audit passes.
- Trial direct access matrix audit passes.
- High-risk role matrix audit passes.
- Finance blueprint menu audit still passes.
- Compile, source integrity, prelaunch, and CRUD completeness checks pass.
