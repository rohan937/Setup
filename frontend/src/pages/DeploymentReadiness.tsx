import { useEffect, useState } from "react";
import { getDeploymentReadiness } from "@/lib/api";
import type {
  DeploymentReadinessResponse,
  DeploymentReadinessCategory,
  DeploymentReadinessCheck,
  DeploymentReadinessStatus,
} from "@/types";
import PageHeader from "@/components/PageHeader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function checkStatusColor(status: DeploymentReadinessCheck["status"]): string {
  switch (status) {
    case "pass": return "text-cyan-400";
    case "warning": return "text-amber-400";
    case "fail": return "text-red-400";
    case "manual": return "text-blue-400";
    case "not_applicable": return "text-gray-500";
    default: return "text-text-muted";
  }
}

function checkStatusLabel(status: DeploymentReadinessCheck["status"]): string {
  switch (status) {
    case "pass": return "PASS";
    case "warning": return "WARN";
    case "fail": return "FAIL";
    case "manual": return "MANUAL";
    case "not_applicable": return "N/A";
    default: return (status as string).toUpperCase();
  }
}

function overallStatusBadgeCls(status: DeploymentReadinessStatus): string {
  switch (status) {
    case "local_demo_ready": return "bg-cyan-900/30 text-cyan-400 border-cyan-700/40";
    case "deployment_prep_ready": return "bg-green-900/30 text-green-400 border-green-700/40";
    case "needs_review": return "bg-amber-900/30 text-amber-400 border-amber-700/40";
    case "blocked": return "bg-red-900/30 text-red-400 border-red-700/40";
    default: return "bg-bg-600 text-text-muted border-border";
  }
}

function overallStatusLabel(status: DeploymentReadinessStatus): string {
  switch (status) {
    case "local_demo_ready": return "LOCAL DEMO READY";
    case "deployment_prep_ready": return "DEPLOYMENT PREP READY";
    case "needs_review": return "NEEDS REVIEW";
    case "blocked": return "BLOCKED";
    default: return (status as string).replace(/_/g, " ").toUpperCase();
  }
}

function categoryStatusColor(status: DeploymentReadinessCategory["status"]): string {
  switch (status) {
    case "pass": return "text-cyan-400";
    case "warning": return "text-amber-400";
    case "fail": return "text-red-400";
    case "manual": return "text-blue-400";
    default: return "text-text-muted";
  }
}

function severityBadgeCls(severity: DeploymentReadinessCheck["severity"]): string {
  switch (severity) {
    case "critical": return "bg-red-900/40 text-red-300 border-red-700/40";
    case "high": return "bg-orange-900/40 text-orange-300 border-orange-700/40";
    case "medium": return "bg-amber-900/40 text-amber-200 border-amber-700/40";
    case "low": return "bg-blue-900/40 text-blue-300 border-blue-700/40";
    case "info": return "bg-bg-600 text-text-muted border-border";
    default: return "bg-bg-600 text-text-muted border-border";
  }
}

function scoreColor(score: number): string {
  if (score >= 90) return "text-cyan-400";
  if (score >= 70) return "text-amber-400";
  if (score >= 50) return "text-orange-400";
  return "text-red-400";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// CheckRow
// ---------------------------------------------------------------------------

function CheckRow({ check }: { check: DeploymentReadinessCheck }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        className="w-full flex items-start gap-3 px-4 py-2.5 hover:bg-bg-600/30 transition-colors text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <span className={`font-mono text-2xs font-semibold w-12 shrink-0 mt-0.5 ${checkStatusColor(check.status)}`}>
          {checkStatusLabel(check.status)}
        </span>
        <span className={`font-mono text-2xs border rounded px-1 shrink-0 mt-0.5 ${severityBadgeCls(check.severity)}`}>
          {check.severity}
        </span>
        <span className="font-mono text-xs text-text-primary flex-1">{check.title}</span>
        <span className="font-mono text-2xs text-text-muted ml-2 shrink-0 mt-0.5">{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-3 pt-0 space-y-1.5 bg-bg-700/30">
          <p className="font-mono text-xs text-text-secondary">{check.explanation}</p>
          {(check.observed_value !== null || check.expected_value !== null) && (
            <div className="flex gap-4 font-mono text-2xs text-text-muted">
              {check.observed_value !== null && (
                <span>observed: <span className="text-text-secondary">{check.observed_value}</span></span>
              )}
              {check.expected_value !== null && (
                <span>expected: <span className="text-text-secondary">{check.expected_value}</span></span>
              )}
            </div>
          )}
          {check.suggested_action && (
            <div className="flex items-start gap-1.5">
              <span className="font-mono text-2xs text-accent-500 mt-0.5">→</span>
              <p className="font-mono text-2xs text-text-secondary">{check.suggested_action}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CategorySection
// ---------------------------------------------------------------------------

function CategorySection({ cat }: { cat: DeploymentReadinessCategory }) {
  const [open, setOpen] = useState(cat.status === "fail" || cat.status === "warning");
  return (
    <div className="rounded-card border border-border bg-bg-700">
      <button
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-bg-600/20 transition-colors text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`font-mono text-2xs font-semibold w-10 shrink-0 ${categoryStatusColor(cat.status)}`}>
          {cat.status.toUpperCase()}
        </span>
        <span className="font-mono text-xs text-text-primary font-semibold flex-1">{cat.title}</span>
        <span className="font-mono text-2xs text-cyan-400 mr-1">{cat.pass_count}P</span>
        {cat.warning_count > 0 && (
          <span className="font-mono text-2xs text-amber-400 mr-1">{cat.warning_count}W</span>
        )}
        {cat.fail_count > 0 && (
          <span className="font-mono text-2xs text-red-400 mr-1">{cat.fail_count}F</span>
        )}
        {cat.manual_count > 0 && (
          <span className="font-mono text-2xs text-blue-400 mr-1">{cat.manual_count}M</span>
        )}
        <span className="font-mono text-2xs text-text-muted ml-1">{open ? "▲" : "▼"}</span>
      </button>
      {open && cat.checks.length > 0 && (
        <div className="border-t border-border">
          {cat.checks.map((c) => (
            <CheckRow key={c.check_key} check={c} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DeploymentReadiness() {
  const [data, setData] = useState<DeploymentReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getDeploymentReadiness()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
        <PageHeader title="Deployment Readiness" />
        <p className="font-mono text-xs text-text-muted animate-pulse">Running readiness checks...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
        <PageHeader title="Deployment Readiness" />
        <div className="rounded-card border border-red-700/40 bg-red-900/20 px-4 py-3">
          <p className="font-mono text-xs text-red-400">Error: {error}</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="flex flex-col gap-4 px-6 py-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <PageHeader title="Deployment Readiness" />
        </div>
        <span className={`font-mono text-2xs border rounded px-2 py-0.5 mt-1 shrink-0 ${overallStatusBadgeCls(data.overall_status)}`}>
          {overallStatusLabel(data.overall_status)}
        </span>
      </div>

      {/* Score + timestamp */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex items-center gap-6">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">Readiness Score</p>
          <p className={`font-mono text-2xl font-bold tabular-nums ${scoreColor(data.readiness_score)}`}>
            {data.readiness_score}<span className="text-sm text-text-muted font-normal">/100</span>
          </p>
        </div>
        <div className="flex-1" />
        <div className="flex flex-col gap-0.5 text-right">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">Generated</p>
          <p className="font-mono text-2xs text-text-secondary">{formatDate(data.generated_at)}</p>
        </div>
      </div>

      {/* Deterministic summary */}
      {data.deterministic_summary && (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
          <p className="font-mono text-2xs text-text-muted mb-1 uppercase tracking-wider">Summary</p>
          <p className="font-mono text-xs text-text-secondary">{data.deterministic_summary}</p>
        </div>
      )}

      {/* Count strip */}
      <div className="rounded-card border border-border bg-bg-700 px-4 py-3 flex items-center gap-6 flex-wrap">
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-text-muted">Pass</p>
          <p className="font-mono text-lg font-bold text-cyan-400 tabular-nums">{data.pass_count}</p>
        </div>
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-text-muted">Warning</p>
          <p className="font-mono text-lg font-bold text-amber-400 tabular-nums">{data.warning_count}</p>
        </div>
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-text-muted">Fail</p>
          <p className="font-mono text-lg font-bold text-red-400 tabular-nums">{data.fail_count}</p>
        </div>
        <div className="flex flex-col gap-0.5">
          <p className="font-mono text-2xs text-text-muted">Manual</p>
          <p className="font-mono text-lg font-bold text-blue-400 tabular-nums">{data.manual_count}</p>
        </div>
        {data.blocker_count > 0 && (
          <div className="flex flex-col gap-0.5">
            <p className="font-mono text-2xs text-text-muted">Blockers</p>
            <p className="font-mono text-lg font-bold text-red-400 tabular-nums">{data.blocker_count}</p>
          </div>
        )}
      </div>

      {/* Blockers */}
      {data.blockers.length > 0 && (
        <div className="rounded-card border border-red-700/50 bg-red-900/20 px-4 py-3">
          <p className="font-mono text-2xs text-red-400 uppercase tracking-wider mb-2">Blockers</p>
          <ul className="space-y-1.5">
            {data.blockers.map((b, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-xs text-red-400 mt-0.5 shrink-0">✗</span>
                <span className="font-mono text-xs text-text-secondary">{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="rounded-card border border-amber-700/50 bg-amber-900/20 px-4 py-3">
          <p className="font-mono text-2xs text-amber-400 uppercase tracking-wider mb-2">Warnings</p>
          <ul className="space-y-1.5">
            {data.warnings.map((w, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-xs text-amber-400 mt-0.5 shrink-0">!</span>
                <span className="font-mono text-xs text-text-secondary">{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggested next steps */}
      {data.suggested_next_steps.length > 0 && (
        <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider mb-2">Suggested Next Steps</p>
          <ul className="space-y-1.5">
            {data.suggested_next_steps.map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-2xs text-accent-500 mt-0.5 shrink-0">{i + 1}.</span>
                <span className="font-mono text-xs text-text-secondary">{step}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Categories */}
      {data.categories.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="font-mono text-2xs text-text-muted uppercase tracking-wider">Check Categories</p>
          {data.categories.map((cat) => (
            <CategorySection key={cat.category_key} cat={cat} />
          ))}
        </div>
      )}

      {/* Footer notes */}
      <div className="flex flex-col gap-1 pt-1 pb-2">
        <p className="font-mono text-2xs text-text-muted">
          M65 checks readiness only. M66 begins backend deployment prep. No deployment is performed by this page.
        </p>
        <p className="font-mono text-2xs text-text-muted">
          No external APIs required. No secrets needed.
        </p>
      </div>
    </div>
  );
}
