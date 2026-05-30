import { useEffect, useState } from "react";
import { fetchApiInfo } from "@/lib/api";

type BackendState =
  | { status: "loading" }
  | { status: "online"; environment: string }
  | { status: "offline" };

export default function Topbar() {
  const [state, setState] = useState<BackendState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    fetchApiInfo()
      .then((info) => {
        if (active) setState({ status: "online", environment: info.environment });
      })
      .catch(() => {
        if (active) setState({ status: "offline" });
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-bg-800 px-6">
      <div className="flex items-center gap-3">
        <span className="caption">Organization</span>
        <span className="text-sm text-text-secondary">Local Workspace</span>
      </div>

      <div className="flex items-center gap-2">
        <BackendBadge state={state} />
      </div>
    </header>
  );
}

function BackendBadge({ state }: { state: BackendState }) {
  const map = {
    loading: { dot: "bg-text-muted", label: "Connecting…", text: "text-text-muted" },
    online: { dot: "bg-severity-success", label: "Backend online", text: "text-text-secondary" },
    offline: { dot: "bg-severity-critical", label: "Backend offline", text: "text-severity-critical" },
  } as const;

  const key = state.status;
  const cfg = map[key];

  return (
    <span className="flex items-center gap-2 rounded-control border border-border bg-bg-700 px-3 py-1.5">
      <span className={`h-2 w-2 rounded-full ${cfg.dot}`} />
      <span className={`text-xs ${cfg.text}`}>
        {cfg.label}
        {state.status === "online" ? ` · ${state.environment}` : ""}
      </span>
    </span>
  );
}
