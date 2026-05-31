import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { ReportDetail, ReportRead, ReportSection, ReportType } from "@/types";
import { getReports, getReport } from "@/lib/api";

// ---------------------------------------------------------------------------
// Colour / label helpers
// ---------------------------------------------------------------------------

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-muted";
  if (score >= 90) return "text-fidelity-high";
  if (score >= 75) return "text-fidelity-high";
  if (score >= 50) return "text-fidelity-medium";
  return "text-fidelity-low";
}

function scoreBarColor(score: number | null): string {
  if (score === null) return "bg-bg-600";
  if (score >= 75) return "bg-fidelity-high";
  if (score >= 50) return "bg-fidelity-medium";
  return "bg-fidelity-low";
}

function severityBadge(sev: string | null): string {
  switch (sev) {
    case "high":
    case "critical":
      return "border-fidelity-low/30 bg-fidelity-low/10 text-fidelity-low";
    case "medium":
      return "border-fidelity-medium/30 bg-fidelity-medium/10 text-fidelity-medium";
    case "low":
      return "border-blue-700/30 bg-blue-900/10 text-blue-400";
    default:
      return "border-border bg-bg-600 text-text-muted";
  }
}

const REPORT_TYPE_LABEL: Record<ReportType, string> = {
  strategy_reliability: "Strategy",
  backtest_audit: "Backtest",
  dataset_health: "Dataset",
};

const REPORT_TYPE_STYLE: Record<ReportType, string> = {
  strategy_reliability: "border-blue-700/40 bg-blue-900/20 text-blue-400",
  backtest_audit: "border-orange-700/40 bg-orange-900/20 text-orange-400",
  dataset_health: "border-violet-700/40 bg-violet-900/20 text-violet-400",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function fmtDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Small chips / badges
// ---------------------------------------------------------------------------

function ReportTypeBadge({ type }: { type: ReportType }) {
  const label = REPORT_TYPE_LABEL[type] ?? type.replace(/_/g, " ");
  const style = REPORT_TYPE_STYLE[type] ?? "border-border bg-bg-600 text-text-muted";
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${style}`}
    >
      {label}
    </span>
  );
}

function SeverityChip({ severity }: { severity: string | null }) {
  if (!severity) return null;
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none ${severityBadge(severity)}`}
    >
      {severity}
    </span>
  );
}

function ScoreChip({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <span className="font-mono text-xs text-text-muted">n/a</span>
    );
  }
  return (
    <span className={`mono-num font-semibold text-sm ${scoreColor(score)}`}>
      {score}
      <span className="text-2xs font-normal text-text-muted">/100</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Report list row
// ---------------------------------------------------------------------------

function ReportRow({
  report,
  onSelect,
}: {
  report: ReportRead;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      className="w-full text-left"
      onClick={() => onSelect(report.id)}
    >
      <div className="flex items-start gap-3 rounded-control border border-border bg-bg-800 px-4 py-3 hover:border-accent-500/40 hover:bg-bg-700 transition-colors">
        {/* Score column */}
        <div className="w-14 shrink-0 text-right pt-0.5">
          <ScoreChip score={report.score} />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <ReportTypeBadge type={report.report_type} />
            <span className="text-xs font-medium text-text-primary truncate">
              {report.title}
            </span>
          </div>
          <p className="text-2xs text-text-muted leading-relaxed line-clamp-2">
            {report.summary}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-2xs text-text-muted">
            <span>{fmtDateShort(report.generated_at)}</span>
            {report.source_type && (
              <span className="text-text-muted/60">
                {report.source_type.replace(/_/g, " ")}
              </span>
            )}
          </div>
        </div>

        {/* Arrow */}
        <span className="shrink-0 mt-1 font-mono text-text-muted/40 text-xs">›</span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Report detail section row
// ---------------------------------------------------------------------------

function SectionRow({ section }: { section: ReportSection }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-border last:border-0">
      <button
        className="flex w-full items-start gap-2.5 px-4 py-3 text-left hover:bg-bg-700/50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Order badge */}
        <span className="mt-0.5 w-5 shrink-0 text-center font-mono text-2xs text-text-muted/50">
          {section.order_index + 1}
        </span>
        {/* Content */}
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-text-primary">
              {section.title}
            </span>
            {section.severity && <SeverityChip severity={section.severity} />}
          </div>
          <p className="text-2xs text-text-secondary leading-relaxed">
            {section.summary}
          </p>
        </div>
        <span className="shrink-0 font-mono text-2xs text-text-muted/50">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && section.evidence_json && (
        <div className="bg-bg-900/50 px-4 pb-4 pt-2 ml-7">
          <pre className="whitespace-pre-wrap break-all font-mono text-2xs text-text-muted leading-relaxed overflow-auto max-h-80">
            {JSON.stringify(section.evidence_json, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Report detail view
// ---------------------------------------------------------------------------

function ReportDetailView({
  reportId,
  onBack,
}: {
  reportId: string;
  onBack: () => void;
}) {
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getReport(reportId)
      .then(setReport)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [reportId]);

  if (loading) {
    return (
      <div className="py-16 text-center font-mono text-xs text-text-muted">
        loading report…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 p-4 text-sm text-fidelity-low">
        {error}
      </div>
    );
  }
  if (!report) return null;

  const sections = [...report.sections].sort(
    (a, b) => a.order_index - b.order_index,
  );

  return (
    <div className="space-y-5">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 font-mono text-xs text-accent-500 hover:text-accent-300"
      >
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
          <path
            d="M7.5 2L3.5 6l4 4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        back to reports
      </button>

      {/* Header card */}
      <div className="rounded-card border border-border bg-bg-700 p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <ReportTypeBadge type={report.report_type} />
              <span
                className={`inline-block rounded border px-1.5 py-0.5 font-mono text-2xs leading-none
                  ${report.status === "generated"
                    ? "border-teal-700/40 bg-teal-900/20 text-teal-400"
                    : "border-border bg-bg-600 text-text-muted"
                  }`}
              >
                {report.status}
              </span>
            </div>
            <h2 className="text-base font-semibold text-text-primary leading-snug">
              {report.title}
            </h2>
            <p className="text-xs text-text-secondary leading-relaxed">
              {report.summary}
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs text-text-muted pt-1">
              <span>Generated {fmtDate(report.generated_at)}</span>
              {report.source_type && (
                <span>Source: {report.source_type.replace(/_/g, " ")}</span>
              )}
              {report.sections.length > 0 && (
                <span>{report.sections.length} section{report.sections.length !== 1 ? "s" : ""}</span>
              )}
            </div>
          </div>

          {/* Score pill */}
          <div className="shrink-0 text-center">
            {report.score !== null ? (
              <div className="space-y-1.5">
                <p className={`mono-num text-3xl font-bold leading-none ${scoreColor(report.score)}`}>
                  {report.score}
                </p>
                <p className="font-mono text-2xs text-text-muted">/ 100</p>
                <div className="h-1 w-16 rounded-full bg-bg-600">
                  <div
                    className={`h-1 rounded-full transition-all ${scoreBarColor(report.score)}`}
                    style={{ width: `${report.score}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <p className="mono-num text-lg font-medium text-text-muted">n/a</p>
                <p className="font-mono text-2xs text-text-muted/60">no score</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sections */}
      <div className="rounded-card border border-border bg-bg-700 overflow-hidden">
        <div className="border-b border-border px-4 py-2.5">
          <p className="caption">Report Sections</p>
        </div>
        {sections.length === 0 ? (
          <p className="px-4 py-4 font-mono text-xs text-text-muted">No sections.</p>
        ) : (
          <div>
            {sections.map((s) => (
              <SectionRow key={s.id} section={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const FILTER_TYPES: { value: string; label: string }[] = [
  { value: "", label: "All types" },
  { value: "strategy_reliability", label: "Strategy" },
  { value: "backtest_audit", label: "Backtest" },
  { value: "dataset_health", label: "Dataset" },
];

function FilterBar({
  reportType,
  onTypeChange,
}: {
  reportType: string;
  onTypeChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="caption">Filter:</span>
      {FILTER_TYPES.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onTypeChange(opt.value)}
          className={`rounded-control border px-2.5 py-1 font-mono text-2xs transition-colors
            ${reportType === opt.value
              ? "border-accent-500/60 bg-accent-500/10 text-accent-300"
              : "border-border bg-bg-700 text-text-muted hover:border-border-focus hover:text-text-secondary"
            }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

export default function Reports() {
  const navigate = useNavigate();
  const { id: reportIdFromUrl } = useParams<{ id?: string }>();

  const [reports, setReports] = useState<ReportRead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(
    reportIdFromUrl ?? null,
  );

  // Sync URL param → state
  useEffect(() => {
    if (reportIdFromUrl) setSelectedId(reportIdFromUrl);
  }, [reportIdFromUrl]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getReports({
      report_type: filterType ? (filterType as ReportType) : undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((resp) => {
        setReports(resp.items);
        setTotal(resp.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filterType, page]);

  function handleSelect(id: string) {
    setSelectedId(id);
    navigate(`/reports/${id}`, { replace: false });
  }

  function handleBack() {
    setSelectedId(null);
    navigate("/reports", { replace: false });
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Detail view
  if (selectedId) {
    return (
      <div className="space-y-5">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Report</h1>
        </div>
        <ReportDetailView reportId={selectedId} onBack={handleBack} />
      </div>
    );
  }

  // List view
  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Reports</h1>
          <p className="mt-1 text-xs text-text-muted">
            Deterministic reliability reports generated from existing evidence.
            Generate reports from Strategy, Backtest, or Dataset pages.
          </p>
        </div>
        <div className="shrink-0 font-mono text-2xs text-text-muted pt-1">
          {total} report{total !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Filter bar */}
      <FilterBar reportType={filterType} onTypeChange={(v) => { setFilterType(v); setPage(0); }} />

      {/* Error state */}
      {error && (
        <div className="rounded-control border border-fidelity-low/30 bg-fidelity-low/10 p-3 font-mono text-xs text-fidelity-low">
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="py-12 text-center font-mono text-xs text-text-muted">
          loading reports…
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && reports.length === 0 && (
        <div className="rounded-card border border-border bg-bg-700 px-6 py-10 text-center">
          <p className="text-sm font-medium text-text-secondary">No reports yet</p>
          <p className="mt-1 text-xs text-text-muted">
            Generate a reliability report from a Strategy or Backtest page.
          </p>
        </div>
      )}

      {/* Report list */}
      {!loading && reports.length > 0 && (
        <div className="space-y-2">
          {reports.map((r) => (
            <ReportRow key={r.id} report={r} onSelect={handleSelect} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-control border border-border px-3 py-1.5 font-mono text-xs text-text-muted
              hover:border-border-focus hover:text-text-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ← prev
          </button>
          <span className="font-mono text-2xs text-text-muted">
            page {page + 1} of {totalPages}
          </span>
          <button
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            className="rounded-control border border-border px-3 py-1.5 font-mono text-xs text-text-muted
              hover:border-border-focus hover:text-text-secondary disabled:opacity-40 disabled:cursor-not-allowed"
          >
            next →
          </button>
        </div>
      )}
    </div>
  );
}
