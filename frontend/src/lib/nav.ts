import type { NavItem } from "@/types";

export const navItems: NavItem[] = [
  // No section — top-level cockpit items
  { label: "Dashboard",        path: "/" },
  // Research
  { label: "Strategy Lab",     path: "/strategies",           section: "Research" },
  { label: "Compare Strategies", path: "/strategies/compare", section: "Research" },
  // Analysis
  { label: "Portfolio",        path: "/portfolio",         section: "Analysis" },
  { label: "Evidence Matrix",  path: "/evidence/coverage", section: "Analysis" },
  { label: "Audit Trail",      path: "/timeline",    section: "Analysis" },
  { label: "Data Health",      path: "/data-health", section: "Analysis" },
  { label: "Backtest Audit",   path: "/backtests",   section: "Analysis" },
  { label: "Reports",          path: "/reports",     section: "Analysis" },
  { label: "Execution Drift",  path: "/live-drift",  section: "Analysis" },
  // Config
  { label: "Signals",          path: "/alerts",      section: "Config" },
  { label: "Settings",         path: "/settings",    section: "Config" },
];
