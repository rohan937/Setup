import type { NavItem } from "@/types";

export const navItems: NavItem[] = [
  // Overview
  { label: "Home",               path: "/",                section: "Overview" },
  { label: "Dashboard",          path: "/dashboard",       section: "Overview" },
  { label: "Portfolio",          path: "/portfolio",       section: "Overview" },
  { label: "Portfolio Reliability", path: "/portfolio/reliability", section: "Overview" },
  { label: "Command Center",     path: "/command-center",  section: "Overview" },
  // Research
  { label: "Strategies",         path: "/strategies",         section: "Research" },
  { label: "Experiments",        path: "/experiments",        section: "Research" },
  { label: "Backtests",          path: "/backtests",          section: "Research" },
  { label: "Datasets",           path: "/datasets",           section: "Research" },
  { label: "Evidence Matrix",    path: "/evidence/coverage",  section: "Research" },
  // Governance
  { label: "Alerts",             path: "/alerts",             section: "Governance" },
  { label: "Review Cases",       path: "/review-cases",       section: "Governance" },
  { label: "Promotion Gates",    path: "/promotion-gates",    section: "Governance" },
  { label: "Regression Tests",   path: "/regression-tests",   section: "Governance" },
  { label: "Policies",           path: "/policies",           section: "Governance" },
  { label: "SLA Monitor",        path: "/sla-monitor",        section: "Governance" },
  { label: "Audit Trail",        path: "/audit-trail",        section: "Governance" },
  // Developer
  { label: "API Keys",           path: "/settings",                    section: "Developer" },
  { label: "SDK / CI",           path: "/developer/sdk",               section: "Developer" },
  { label: "Evidence Bundles",   path: "/developer/evidence-bundles",  section: "Developer" },
  // Admin
  { label: "Workspace Settings", path: "/workspace/settings",         section: "Admin" },
  { label: "Members",            path: "/workspace/members",          section: "Admin" },
  { label: "System Health",      path: "/admin/system-health",        section: "Admin" },
  { label: "Demo Controls",      path: "/admin/demo-controls",        section: "Admin" },
  { label: "Deployment Readiness", path: "/admin/deployment-readiness", section: "Admin" },
];
