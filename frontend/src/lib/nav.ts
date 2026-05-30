import type { NavItem } from "@/types";

// M1 placeholder navigation. Mirrors the product surface in UIDesignSystem.txt;
// pages are static shells until later milestones wire real data.
export const navItems: NavItem[] = [
  { label: "Dashboard", path: "/" },
  { label: "Strategies", path: "/strategies" },
  { label: "Timeline", path: "/timeline" },
  { label: "Data Health", path: "/data-health" },
  { label: "Backtests", path: "/backtests" },
  { label: "Live Drift", path: "/live-drift" },
  { label: "Alerts", path: "/alerts" },
  { label: "Settings", path: "/settings" },
];
