import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { fetchApiInfo } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

type BackendState =
  | { status: "loading" }
  | { status: "online"; environment: string }
  | { status: "offline" };

function deriveArea(pathname: string): string {
  if (
    pathname === "/" ||
    pathname === "/dashboard" ||
    pathname === "/command-center" ||
    pathname === "/audit-trail"
  ) {
    return "Command";
  }
  if (
    pathname.startsWith("/strategies") ||
    pathname.startsWith("/backtests") ||
    pathname.startsWith("/experiments") ||
    pathname.startsWith("/datasets") ||
    pathname.startsWith("/evidence")
  ) {
    return "Research";
  }
  if (pathname.startsWith("/portfolio")) {
    return "Portfolio";
  }
  if (
    pathname === "/alerts" ||
    pathname === "/review-cases" ||
    pathname === "/governance" ||
    pathname === "/promotion-gates" ||
    pathname === "/regression-tests" ||
    pathname === "/policies" ||
    pathname === "/sla-monitor"
  ) {
    return "Governance";
  }
  if (pathname.startsWith("/developer") || pathname.startsWith("/settings")) {
    return "Developer";
  }
  if (pathname.startsWith("/workspace") || pathname.startsWith("/admin")) {
    return "Admin";
  }
  return "QuantFidelity";
}

export default function Topbar() {
  const [state, setState] = useState<BackendState>({ status: "loading" });
  const { user, isAuthenticated, logout } = useAuth();
  const { pathname } = useLocation();
  const area = deriveArea(pathname);

  useEffect(() => {
    let active = true;
    fetchApiInfo()
      .then((info) => {
        if (active) setState({ status: "online", environment: info.environment });
      })
      .catch(() => {
        if (active) setState({ status: "offline" });
      });
    return () => { active = false; };
  }, []);

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-bg-800 px-5 gap-4">
      <div className="flex items-center gap-2">
        <span className="caption text-text-muted">QuantFidelity</span>
        <span className="text-text-muted">/</span>
        <span className="text-2xs font-medium uppercase tracking-eyebrow text-text-secondary">
          {area}
        </span>
      </div>
      <div className="flex items-center gap-4">
      <span className="font-mono text-2xs text-text-muted uppercase tracking-widest">
        ENV:&nbsp;
        <span className="text-text-secondary">
          {state.status === "online" ? state.environment : "—"}
        </span>
      </span>
      <ApiStatus state={state} />
      {isAuthenticated && user ? (
        <span className="flex items-center gap-3">
          <span className="font-mono text-2xs text-text-secondary" title={user.email}>
            {user.display_name}
          </span>
          <button
            onClick={() => logout()}
            className="font-mono text-2xs text-text-muted hover:text-fidelity-low uppercase tracking-widest transition-colors"
          >
            Sign Out
          </button>
        </span>
      ) : (
        <Link
          to="/login"
          className="font-mono text-2xs text-text-muted hover:text-brand uppercase tracking-widest transition-colors"
        >
          Sign In
        </Link>
      )}
      </div>
    </header>
  );
}

function ApiStatus({ state }: { state: BackendState }) {
  const cfg = {
    loading: { dot: "bg-text-muted",    ring: "bg-text-muted/30",    text: "text-text-muted",     label: "API connecting" },
    online:  { dot: "bg-fidelity-high", ring: "bg-fidelity-high/40", text: "text-fidelity-high",  label: "API online" },
    offline: { dot: "bg-fidelity-low",  ring: "bg-fidelity-low/40",  text: "text-fidelity-low",   label: "API offline" },
  }[state.status];

  return (
    <span className="flex items-center gap-1.5">
      <span className="relative flex h-1.5 w-1.5 items-center justify-center">
        <span
          className={`absolute inline-flex h-2.5 w-2.5 rounded-full animate-soft-pulse ${cfg.ring}`}
          aria-hidden="true"
        />
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      </span>
      <span className={`font-mono text-2xs uppercase tracking-widest ${cfg.text}`}>
        {cfg.label}
      </span>
    </span>
  );
}
