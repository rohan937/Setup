import type {
  StrategyLifecycleResponse,
  LifecycleStage,
  LifecycleBlocker,
} from "@/types";

interface StrategyLifecycleBarProps {
  data: StrategyLifecycleResponse;
  onBlockerAction: (blocker: LifecycleBlocker) => void;
  compact?: boolean;
}

const stageNodeClasses: Record<LifecycleStage["state"], string> = {
  completed: "border-fidelity-high/40 bg-fidelity-high/10 text-fidelity-high state-glow-success",
  current: "border-accent-500 bg-accent-500/20 text-accent-200 state-glow-primary",
  blocked: "border-fidelity-medium/60 bg-fidelity-medium/10 text-fidelity-medium",
  upcoming: "border-border bg-bg-800 text-text-muted",
};

const stageLabelClasses: Record<LifecycleStage["state"], string> = {
  completed: "text-text-secondary",
  current: "text-accent-200",
  blocked: "text-fidelity-medium",
  upcoming: "text-text-muted",
};

const connectorClasses: Record<LifecycleStage["state"], string> = {
  completed: "bg-fidelity-high/30",
  current: "bg-accent-500/40",
  blocked: "bg-fidelity-medium/30",
  upcoming: "bg-border",
};

const severityChipClasses: Record<string, string> = {
  critical: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  high: "border-fidelity-low/40 bg-fidelity-low/10 text-fidelity-low",
  medium: "border-fidelity-medium/40 bg-fidelity-medium/10 text-fidelity-medium",
};

function severityClasses(severity: string): string {
  return (
    severityChipClasses[severity.toLowerCase()] ??
    "border-border bg-bg-800 text-text-muted"
  );
}

export default function StrategyLifecycleBar({
  data,
  onBlockerAction,
  compact = false,
}: StrategyLifecycleBarProps) {
  return (
    <div className="rounded-card border border-border bg-bg-700 shadow-card animate-fade-in">
      <div
        className={
          "border-b border-border " +
          (compact ? "px-3 py-2" : "px-4 py-3")
        }
      >
        <div className="caption">Lifecycle</div>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="text-sm text-text-primary">
            Current: {data.current_stage_label}
            {data.next_stage_label ? (
              <span className="text-text-secondary">
                {" "}
                &rarr; Next: {data.next_stage_label}
              </span>
            ) : null}
          </span>
          {data.blocked && data.blocked_stage_label ? (
            <span className="rounded-chip border border-fidelity-medium/40 bg-fidelity-medium/10 px-1.5 py-px text-2xs text-fidelity-medium">
              Blocked from {data.blocked_stage_label}
            </span>
          ) : null}
        </div>
      </div>

      <div className={compact ? "px-3 py-3" : "px-4 py-4"}>
        <div className="overflow-x-auto">
          <div className="flex min-w-max items-start">
            {data.stages.map((stage, idx) => (
              <div key={stage.key} className="flex items-start">
                <div className="flex w-20 flex-col items-center">
                  <div
                    className={
                      "flex h-7 w-7 items-center justify-center rounded-full border text-2xs font-semibold transition-all duration-200 " +
                      stageNodeClasses[stage.state] +
                      (stage.state === "current"
                        ? " ring-2 ring-accent-500/30 animate-soft-pulse"
                        : "")
                    }
                  >
                    {stage.index + 1}
                  </div>
                  <span
                    className={
                      "mt-1.5 text-center text-2xs leading-tight " +
                      stageLabelClasses[stage.state]
                    }
                  >
                    {stage.label}
                  </span>
                </div>
                {idx < data.stages.length - 1 ? (
                  <div
                    className={
                      "mt-3.5 h-px w-8 shrink-0 " + connectorClasses[stage.state]
                    }
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div className={compact ? "mt-3" : "mt-4"}>
          <div className="caption">What blocks progression?</div>
          {data.blockers.length === 0 ? (
            <p className="mt-1.5 text-xs">
              {data.next_stage ? (
                <span className="text-fidelity-high">
                  No progression blockers &mdash; ready to advance.
                </span>
              ) : (
                <span className="text-text-secondary">
                  This strategy has reached the final tracked stage.
                </span>
              )}
            </p>
          ) : (
            <ul className="mt-2 space-y-2">
              {data.blockers.map((blocker, idx) => (
                <li
                  key={`${blocker.action_type}-${idx}`}
                  className="flex items-start gap-3 rounded-control border border-border bg-bg-800 px-3 py-2"
                >
                  <span
                    className={
                      "mt-0.5 shrink-0 rounded-chip border px-1.5 py-px text-2xs capitalize " +
                      severityClasses(blocker.severity)
                    }
                  >
                    {blocker.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-text-primary">
                      {blocker.reason}
                    </div>
                    <div className="text-xs text-text-secondary">
                      {blocker.detail}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onBlockerAction(blocker)}
                    className="shrink-0 rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
                  >
                    {blocker.action_label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {!compact ? (
        <div className="border-t border-border px-4 py-2">
          <p className="text-2xs text-text-muted">{data.disclaimer}</p>
        </div>
      ) : null}
    </div>
  );
}
