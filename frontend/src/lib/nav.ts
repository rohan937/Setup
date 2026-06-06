import type { NavItem } from "@/types";

export interface NavGroup {
  id: string;
  label: string;
  defaultExpanded: boolean;
  items: NavItem[];
}

/** Standalone top-level item, rendered above the groups (not inside a group). */
export const homeItem: NavItem = { label: "Home", path: "/" };

export const navGroups: NavGroup[] = [
  {
    id: "research",
    label: "Research",
    defaultExpanded: true,
    items: [
      { label: "Strategies", path: "/strategies" },
      { label: "Backtests", path: "/backtests" },
      { label: "Experiments", path: "/experiments" },
      { label: "Datasets", path: "/data-health" },
      { label: "Evidence", path: "/evidence/coverage" },
    ],
  },
  {
    id: "portfolio",
    label: "Portfolio",
    defaultExpanded: true,
    items: [
      { label: "Overview", path: "/portfolio" },
      { label: "Reliability", path: "/portfolio/reliability" },
    ],
  },
  {
    id: "governance",
    label: "Governance",
    defaultExpanded: true,
    items: [
      { label: "Alerts", path: "/alerts" },
      { label: "Reviews", path: "/governance/strategy-reviews" },
      { label: "Promotion", path: "/promotion-gates" },
      { label: "Cases", path: "/review-cases" },
      { label: "Policies", path: "/policies" },
    ],
  },
  {
    id: "command",
    label: "Command",
    defaultExpanded: true,
    items: [
      { label: "Command Center", path: "/command-center" },
      { label: "Dashboard", path: "/dashboard" },
      { label: "Audit Trail", path: "/audit-trail" },
    ],
  },
  {
    id: "quality",
    label: "Quality",
    defaultExpanded: false,
    items: [
      { label: "Regression", path: "/regression-tests" },
      { label: "SLA Monitor", path: "/sla-monitor" },
    ],
  },
  {
    id: "developer",
    label: "Developer",
    defaultExpanded: false,
    items: [
      { label: "Bundle Builder", path: "/developer/evidence-builder" },
      { label: "Evidence Bundles", path: "/developer/evidence-bundles" },
      { label: "SDK / CI", path: "/developer/sdk" },
      { label: "API Keys", path: "/settings" },
    ],
  },
  {
    id: "admin",
    label: "Admin",
    defaultExpanded: false,
    items: [
      { label: "System Health", path: "/admin/system-health" },
      { label: "Demo Controls", path: "/admin/demo-controls" },
      { label: "Deployment Readiness", path: "/admin/deployment-readiness" },
      { label: "Workspace Settings", path: "/workspace/settings" },
      { label: "Members", path: "/workspace/members" },
    ],
  },
];

/** IDs of secondary (de-emphasized) groups, rendered below a divider. */
export const secondaryGroupIds = new Set(["quality", "developer", "admin"]);

/** Backward-compatible flat list: Home + every grouped item, in order. */
export const navItems: NavItem[] = [homeItem, ...navGroups.flatMap((g) => g.items)];
