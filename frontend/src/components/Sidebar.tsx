import { NavLink } from "react-router-dom";
import { navItems } from "@/lib/nav";
import type { NavItem } from "@/types";

// Group nav items by section, preserving insertion order
function groupNavItems(items: NavItem[]) {
  const groups: { section: string | null; items: NavItem[] }[] = [];
  for (const item of items) {
    const section = item.section ?? null;
    const last = groups[groups.length - 1];
    if (last && last.section === section) {
      last.items.push(item);
    } else {
      groups.push({ section, items: [item] });
    }
  }
  return groups;
}

const groups = groupNavItems(navItems);

export default function Sidebar() {
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

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-4">
        {groups.map(({ section, items }, groupIdx) => (
          <div key={section ?? "_root"} className={groupIdx === 0 ? "mt-0" : "mt-5"}>
            {section && (
              <p className="caption mb-2 px-4">{section}</p>
            )}
            <ul className="space-y-0.5 px-2.5">
              {items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) =>
                      [
                        "relative flex items-center rounded-control px-3 py-2 text-[0.8125rem] transition-colors",
                        isActive
                          ? "bg-brand/10 font-medium text-text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-brand"
                          : "text-text-muted hover:bg-bg-700/60 hover:text-text-secondary",
                      ].join(" ")
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
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
