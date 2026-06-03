import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchApiInfo } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

type BackendState =
  | { status: "loading" }
  | { status: "online"; environment: string }
  | { status: "offline" };

export default function Topbar() {
  const [state, setState] = useState<BackendState>({ status: "loading" });
  const { user, isAuthenticated, logout } = useAuth();

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
    <header className="flex h-10 shrink-0 items-center justify-end border-b border-border bg-bg-800 px-5 gap-4">
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
    </header>
  );
}

function ApiStatus({ state }: { state: BackendState }) {
  const cfg = {
    loading: { dot: "bg-text-muted",         text: "text-text-muted",     label: "API connecting" },
    online:  { dot: "bg-fidelity-high",       text: "text-fidelity-high",  label: "API online" },
    offline: { dot: "bg-fidelity-low animate-pulse", text: "text-fidelity-low", label: "API offline" },
  }[state.status];

  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      <span className={`font-mono text-2xs uppercase tracking-widest ${cfg.text}`}>
        {cfg.label}
      </span>
    </span>
  );
}
