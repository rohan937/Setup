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
    <aside className="flex w-52 shrink-0 flex-col border-r border-border bg-bg-800">
      {/* Logo mark */}
      <div className="flex h-11 items-center gap-2.5 border-b border-border px-4">
        <span className="font-mono text-xs font-bold tracking-tight text-accent-500">
          [QF]
        </span>
        <span className="text-xs font-semibold tracking-tight text-text-primary">
          QuantFidelity
        </span>
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-3">
        {groups.map(({ section, items }) => (
          <div key={section ?? "_root"} className="mb-1">
            {section && (
              <p className="caption mb-1 px-4 pt-2">{section}</p>
            )}
            <ul className="space-y-px px-2">
              {items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) =>
                      [
                        "flex items-center rounded-control py-1.5 pl-[10px] pr-3 text-xs transition-colors",
                        "border-l-2",
                        isActive
                          ? "border-accent-500 bg-bg-600 font-medium text-accent-300"
                          : "border-transparent text-text-muted hover:bg-bg-600/60 hover:text-text-secondary",
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

      {/* Footer */}
      <div className="border-t border-border px-4 py-3">
        <p className="font-mono text-2xs text-text-muted">
          M3 · Strategy Lab
        </p>
      </div>
    </aside>
  );
}
