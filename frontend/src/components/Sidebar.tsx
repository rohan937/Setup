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
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-bg-800">
      {/* Logo mark */}
      <div className="flex h-12 items-center gap-2.5 border-b border-border px-4">
        <span className="flex h-6 w-6 items-center justify-center rounded-control bg-bg-600 font-mono text-[0.625rem] font-semibold tracking-tight text-accent-300">
          QF
        </span>
        <span className="text-sm font-semibold tracking-tight text-text-primary">
          QuantFidelity
        </span>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-4">
        {groups.map(({ section, items }) => (
          <div key={section ?? "_root"} className="mb-4">
            {section && (
              <p className="caption mb-1.5 px-4">{section}</p>
            )}
            <ul className="space-y-0.5 px-2.5">
              {items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) =>
                      [
                        "flex items-center rounded-control px-2.5 py-1.5 text-[0.8125rem] transition-colors",
                        isActive
                          ? "bg-bg-600 font-medium text-text-primary"
                          : "text-text-muted hover:bg-bg-700/70 hover:text-text-secondary",
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
      <div className="border-t border-border px-4 py-3">
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
