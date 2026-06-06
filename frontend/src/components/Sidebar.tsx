import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { navGroups, homeItem, secondaryGroupIds } from "@/lib/nav";
import type { NavGroup } from "@/lib/nav";

const itemClass = ({ isActive }: { isActive: boolean }) =>
  [
    "relative flex items-center rounded-control px-3 py-2 text-[0.8125rem] transition-colors",
    isActive
      ? "bg-brand/10 font-medium text-text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-brand"
      : "text-text-muted hover:bg-bg-700/60 hover:text-text-secondary",
  ].join(" ");

function groupHasActive(group: NavGroup, pathname: string) {
  return group.items.some(
    (it) =>
      pathname === it.path ||
      (it.path !== "/" && pathname.startsWith(it.path)),
  );
}

export default function Sidebar() {
  const { pathname } = useLocation();

  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      navGroups.map((g) => [g.id, g.defaultExpanded || groupHasActive(g, pathname)]),
    ),
  );

  // Deep-linking into a collapsed group should reveal it. Force-expand the group
  // that owns the now-active route without collapsing the others.
  useEffect(() => {
    setExpanded((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const g of navGroups) {
        if (groupHasActive(g, pathname) && !next[g.id]) {
          next[g.id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [pathname]);

  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const renderGroup = (group: NavGroup) => {
    const isOpen = expanded[group.id];
    const isSecondary = secondaryGroupIds.has(group.id);
    return (
      <div key={group.id} className="mt-5">
        <button
          type="button"
          onClick={() => toggle(group.id)}
          aria-expanded={isOpen}
          className={[
            "group/header flex w-full items-center justify-between px-4 py-1 transition-colors",
            isSecondary ? "text-text-muted" : "text-text-secondary",
            "hover:text-text-secondary",
          ].join(" ")}
        >
          <span className="caption">{group.label}</span>
          <svg
            viewBox="0 0 16 16"
            aria-hidden="true"
            className={[
              "h-3 w-3 shrink-0 transition-transform duration-200",
              isOpen ? "rotate-90" : "rotate-0",
            ].join(" ")}
          >
            <path
              d="M6 4l4 4-4 4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        {isOpen && (
          <ul className="animate-fade-in mt-1 space-y-0.5 px-2.5">
            {group.items.map((item) => (
              <li key={item.path}>
                <NavLink to={item.path} className={itemClass}>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  const primaryGroups = navGroups.filter((g) => !secondaryGroupIds.has(g.id));
  const secondaryGroups = navGroups.filter((g) => secondaryGroupIds.has(g.id));

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-bg-800">
      {/* Logo mark */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
        <span className="flex h-7 w-7 items-center justify-center rounded-control bg-brand/15 font-mono text-xs font-bold tracking-tight text-accent-300 shadow-glow">
          QF
        </span>
        <span className="text-sm font-semibold tracking-tight text-text-primary">
          QuantFidelity
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4">
        {/* Standalone Home item */}
        <ul className="space-y-0.5 px-2.5">
          <li>
            <NavLink to={homeItem.path} end className={itemClass}>
              {homeItem.label}
            </NavLink>
          </li>
        </ul>

        {/* Primary groups */}
        {primaryGroups.map(renderGroup)}

        {/* Divider between primary and secondary groups */}
        <div className="mx-4 mt-5 border-t border-border" />

        {/* Secondary (de-emphasized) groups */}
        {secondaryGroups.map(renderGroup)}
      </nav>

      {/* Workspace footer */}
      <div className="border-t border-border px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-control bg-bg-600 font-mono text-2xs font-medium text-text-secondary">
            QR
          </span>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-text-secondary">
              Quant Research
            </p>
            <p className="caption mt-0.5 text-text-muted">Workspace</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
