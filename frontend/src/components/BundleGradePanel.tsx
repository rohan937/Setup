import type { BundleGradeResponse, BundleIncludedItem, BundleMissingItem } from "@/types";

export default function BundleGradePanel({ grade }: { grade: BundleGradeResponse }) {
  const gradeColor =
    grade.verdict === "excellent" || grade.verdict === "good" ? "text-teal-400" :
    grade.verdict === "usable" ? "text-amber-400" :
    grade.verdict === "weak" ? "text-orange-400" : "text-red-400";

  const stageColor = (s: string) =>
    s === "pass" ? "text-teal-400" : s === "warning" ? "text-amber-400" : "text-red-400";

  const qualityColor = (q: string) =>
    q === "good" ? "text-teal-400" : q === "fair" ? "text-amber-400" : q === "weak" ? "text-orange-400" : "text-text-muted";

  const STAGE_LABELS: Record<string, string> = {
    research: "Research", backtest_review: "Backtest Review", paper_candidate: "Paper Candidate",
    shadow: "Shadow", production_candidate: "Production Candidate",
  };

  return (
    <div className="rounded-control border border-border bg-bg-800 p-4 space-y-3">
      {/* Header: grade + verdict */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-baseline gap-3">
          <span className={"font-mono text-2xl font-bold " + gradeColor}>{grade.letter_grade}</span>
          <span className="font-mono text-xs text-text-muted">{grade.quality_score.toFixed(0)}/100</span>
          <span className={"font-mono text-xs font-semibold uppercase " + gradeColor}>{grade.verdict}</span>
        </div>
      </div>

      {/* Stage sufficiency */}
      <div>
        <p className="caption mb-1.5">Stage Sufficiency</p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(grade.stage_sufficiency).map(([stage, status]) => (
            <span key={stage} className="rounded border border-border bg-bg-900 px-2 py-1 font-mono text-2xs">
              <span className="text-text-secondary">{STAGE_LABELS[stage] ?? stage}: </span>
              <span className={stageColor(status)}>{status}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Sufficient for / not */}
      {grade.sufficient_for.length > 0 && (
        <p className="font-mono text-2xs text-teal-400">Sufficient for: {grade.sufficient_for.map(s => STAGE_LABELS[s] ?? s).join(", ")}</p>
      )}
      {grade.not_sufficient_for.length > 0 && (
        <p className="font-mono text-2xs text-text-muted">Not yet sufficient for: {grade.not_sufficient_for.map(s => STAGE_LABELS[s] ?? s).join(", ")}</p>
      )}

      {/* Included checklist */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
        {grade.included.map((it: BundleIncludedItem) => (
          <div key={it.key} className="flex items-center gap-1.5 font-mono text-2xs">
            <span>{it.status === "present" ? "✅" : "❌"}</span>
            <span className="text-text-secondary">{it.label}</span>
            {it.status === "present" && <span className={qualityColor(it.quality)}>({it.quality})</span>}
          </div>
        ))}
      </div>

      {/* Missing */}
      {grade.missing.length > 0 && (
        <div>
          <p className="caption mb-1">Missing</p>
          {grade.missing.map((m: BundleMissingItem) => (
            <p key={m.key} className="font-mono text-2xs text-text-muted">
              <span className={m.severity === "high" ? "text-red-400" : m.severity === "medium" ? "text-amber-400" : "text-text-muted"}>•</span> {m.label} — {m.why_it_matters}
            </p>
          ))}
        </div>
      )}

      {/* Warnings */}
      {grade.warnings.length > 0 && (
        <div className="rounded border border-amber-700/30 bg-amber-900/10 px-3 py-2">
          <p className="font-mono text-2xs font-semibold text-amber-400 mb-1">Warnings ({grade.warnings.length})</p>
          {grade.warnings.map((w, i) => <p key={i} className="font-mono text-2xs text-amber-300">{w}</p>)}
        </div>
      )}

      {/* Recommended fixes */}
      {grade.recommended_fixes.length > 0 && (
        <div>
          <p className="caption mb-1">Recommended Fixes</p>
          {grade.recommended_fixes.map((f, i) => <p key={i} className="font-mono text-2xs text-text-secondary">→ {f}</p>)}
        </div>
      )}

      <p className="font-mono text-2xs text-text-muted italic">{grade.disclaimer}</p>
    </div>
  );
}
