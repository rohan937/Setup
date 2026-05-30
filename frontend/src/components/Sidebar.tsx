import { NavLink } from "react-router-dom";
import { navItems } from "@/lib/nav";

export default function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-bg-800">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <span className="h-2.5 w-2.5 rounded-sm bg-accent-500" />
        <span className="text-sm font-semibold tracking-tight text-text-primary">
          QuantFidelity
        </span>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              [
                "block rounded-control px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-bg-600 text-text-primary"
                  : "text-text-secondary hover:bg-bg-700 hover:text-text-primary",
              ].join(" ")
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border px-5 py-3">
        <p className="caption">Milestone</p>
        <p className="mono-num text-xs text-text-secondary">M1 · Foundation</p>
      </div>
    </aside>
  );
}
