# Roles and Permissions

QuantFidelity uses a clear, four-role model to govern who can read research, write reliability evidence, and manage a workspace. This document explains the roles, the underlying permission keys, how access behaves in local development, and how the role-aware access experience guides people who land on a gated screen.

Access control is designed to be calm and informative. Instead of dead-ending users with a blunt refusal, gated screens explain the situation and offer a sensible next step. Access decisions never expose secrets and never suggest editing the database.

## Roles

| Role | Description | Roughly what they can do |
|------|-------------|--------------------------|
| **owner** | Full control of the workspace. | Everything: read and write research, manage workspace settings, manage members, manage API keys, and seed demo data. |
| **admin** | Trusted operator with most management rights. | Read and write research, manage workspace settings, manage members, and manage API keys. Effectively everything an owner can do for day-to-day operation. |
| **member** | Contributor who works with reliability evidence. | Read research and write research evidence. No workspace, member, or API-key management. |
| **viewer** | Read-only observer. | View research and reliability evidence only. No write or management actions. |

## Permissions

Each role is composed from a set of permission keys (the `PermissionSet`). Screens and actions check these keys rather than the role name directly, which keeps gating consistent.

| Permission key | What it unlocks | Roles that typically have it |
|----------------|-----------------|------------------------------|
| `can_read_research` | View strategies, reliability snapshots, evidence, reports, and analytics. | owner, admin, member, viewer |
| `can_write_research` | Create and update research evidence (regression tests, review cases, evidence bundles, and related artifacts). | owner, admin, member |
| `can_manage_workspace` | Change workspace settings and view operational pages such as System Health and Deployment Readiness. | owner, admin |
| `can_manage_members` | Invite, remove, and change the roles of workspace members. | owner, admin |
| `can_manage_api_keys` | Create, rotate, and revoke API keys. | owner, admin |
| `can_seed_demo` | Seed demo data into the workspace. | owner (admin in most workspaces) |

## Local-dev pseudo-owner

In local development with no auth token present, the app behaves as a permissive **pseudo-owner**. All permission checks pass, so the demo is frictionless and every page is reachable without setting up authentication.

This is a convenience for local exploration only. In a deployed or auth-enabled environment, the authenticated user's real role applies and the permission checks above are enforced normally.

## Role-aware access UX (RoleAwareAccess component)

When a user reaches a screen or action they are not permitted to use, QuantFidelity does not show a blunt "Admin access required" message. Instead, the shared `RoleAwareAccess` component presents a calm, informative panel that includes:

- **Current role** — the role the user holds in this workspace.
- **Required role or permission** — what is needed to proceed.
- **What you can still do** — the actions that remain available to the user.
- **A suggested action** — a calm next step, such as asking a workspace owner to upgrade the role, or signing in as an owner/admin account.

For example:

> You need Owner or Admin access to seed demo data. Current role: Member. Ask a workspace owner to upgrade your role, or sign in as an owner/admin account.

The component never exposes secrets (such as API keys or tokens) and never tells the user to edit the database.

**Gated pages that use RoleAwareAccess:**

| Page | Required permission |
|------|---------------------|
| Demo Controls | `can_seed_demo` |
| System Health | `can_manage_workspace` |
| Deployment Readiness | `can_manage_workspace` |
| Workspace Settings / Members | `can_manage_members` |
| API Keys | `can_manage_api_keys` |

## How to change roles

There are two supported ways to obtain the access you need:

1. **Update the member's role** — an owner or admin opens **Workspace → Members** and changes the member's role (for example, from Member to Admin).
2. **Sign in as an owner or admin account** — if you have credentials for a higher-privileged account, sign in with it. For a local demo, sign in as the workspace owner account.

Roles are never changed through manual database edits. Use the Members screen or sign in with the appropriate account.
