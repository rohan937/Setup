import type {
  StrategyScoreExplanationResponse,
  ScoreCard,
  ScoreDriverItem,
} from "@/types";

interface Props {
  open: boolean;
  onClose: () => void;
  data: StrategyScoreExplanationResponse | null;
  loading: boolean;
  error: string | null;
  /** When set, show only the scorecard with this score_key; otherwise show all. */
  focusScoreKey?: string | null;
}

/** Map a verdict string to a tone for color styling. */
function verdictTone(verdict: string): "teal" | "amber" | "red" | "muted" {
  const v = verdict.toLowerCase();
  if (["good", "realistic", "verified", "ready", "stable"].includes(v)) return "teal";
  if (["review", "watch", "acceptable"].includes(v)) return "amber";
  if (["weak", "blocked", "failed", "drifted"].includes(v)) return "red";
  return "muted";
}

const verdictBadgeCls: Record<"teal" | "amber" | "red" | "muted", string> = {
  teal: "border-teal-500/40 bg-teal-500/10 text-teal-300",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  red: "border-red-500/40 bg-red-500/10 text-red-300",
  muted: "border-border bg-bg-700 text-text-muted",
};

function formatPoints(points: number): string {
  const rounded = Math.round(points * 100) / 100;
  return rounded > 0 ? `+${rounded}` : `${rounded}`;
}

function DriverList({
  items,
  tone,
}: {
  items: ScoreDriverItem[];
  tone: "teal" | "red";
}) {
  const accent = tone === "teal" ? "text-teal-300" : "text-red-300";
  const border = tone === "teal" ? "border-teal-500/30" : "border-red-500/30";
  return (
    <ul className="mt-2 space-y-2">
      {items.map((item) => (
        <li
          key={item.key}
          className={`rounded-control border ${border} bg-bg-800/60 px-2.5 py-2`}
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-mono text-xs text-text-primary">{item.label}</span>
            <span className={`font-mono text-2xs ${accent}`}>
              {formatPoints(item.points)}
            </span>
          </div>
          <p className="mt-1 font-mono text-2xs text-text-secondary">
            {item.explanation}
          </p>
          {item.recommended_action ? (
            <p className={`mt-1 font-mono text-2xs ${accent}`}>
              {"→"} {item.recommended_action}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ScoreCardView({ card }: { card: ScoreCard }) {
  const tone = verdictTone(card.verdict);
  const positives = card.items.filter((i) => i.direction === "positive");
  const negatives = card.items.filter((i) => i.direction === "negative");
  const neutrals = card.items.filter((i) => i.direction === "neutral");
  const scoreText =
    card.score == null ? "—" : `${Math.round(card.score * 100) / 100}`;

  return (
    <section className="rounded-control border border-border bg-bg-800 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-mono text-xs font-semibold text-text-primary">
            {card.label}
          </h3>
          <p className="mt-0.5 font-mono text-2xs text-text-muted">
            {scoreText}/{Math.round(card.max_score * 100) / 100}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-control border px-2 py-0.5 font-mono text-2xs uppercase tracking-wide ${verdictBadgeCls[tone]}`}
        >
          {card.verdict.replace(/_/g, " ")}
        </span>
      </div>

      {card.primary_positive ? (
        <p className="mt-2 font-mono text-2xs text-teal-300">
          What helped: {card.primary_positive}
        </p>
      ) : null}
      {card.primary_drag ? (
        <p className="mt-1 font-mono text-2xs text-red-300">
          What hurt: {card.primary_drag}
        </p>
      ) : null}

      {positives.length > 0 ? (
        <div className="mt-3">
          <h4 className="font-mono text-2xs uppercase tracking-wide text-text-muted">
            What helped this score
          </h4>
          <DriverList items={positives} tone="teal" />
        </div>
      ) : null}

      {negatives.length > 0 ? (
        <div className="mt-3">
          <h4 className="font-mono text-2xs uppercase tracking-wide text-text-muted">
            What hurt this score
          </h4>
          <DriverList items={negatives} tone="red" />
        </div>
      ) : null}

      {neutrals.length > 0 ? (
        <div className="mt-3">
          <h4 className="font-mono text-2xs uppercase tracking-wide text-text-muted">
            Other factors
          </h4>
          <ul className="mt-2 space-y-1.5">
            {neutrals.map((item) => (
              <li
                key={item.key}
                className="rounded-control border border-border bg-bg-700/50 px-2.5 py-1.5"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-2xs text-text-secondary">
                    {item.label}
                  </span>
                  <span className="font-mono text-2xs text-text-muted">
                    {formatPoints(item.points)}
                  </span>
                </div>
                <p className="mt-0.5 font-mono text-2xs text-text-muted">
                  {item.explanation}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {card.formula_note ? (
        <p className="mt-3 font-mono text-2xs italic text-text-muted">
          {card.formula_note}
        </p>
      ) : null}
    </section>
  );
}

export default function ScoreExplainDrawer({
  open,
  onClose,
  data,
  loading,
  error,
  focusScoreKey,
}: Props) {
  if (!open) return null;

  const cards = data
    ? focusScoreKey
      ? data.scorecards.filter((c) => c.score_key === focusScoreKey)
      : data.scorecards
    : [];

  return (
    <div className="fixed inset-0 z-40">
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Score Explainability"
        className="fixed right-0 top-0 z-50 flex h-full w-[28rem] max-w-full flex-col overflow-y-auto border-l border-border bg-bg-900 shadow-panel"
      >
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-bg-900 px-4 py-3">
          <h2 className="font-mono text-xs font-semibold uppercase tracking-wide text-text-primary">
            Score Explainability
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-control border border-border bg-bg-700 px-2 py-1 font-mono text-2xs text-text-secondary hover:border-border-hover hover:text-text-primary"
          >
            Close
          </button>
        </header>

        <div className="flex-1 space-y-3 px-4 py-4">
          {loading ? (
            <p className="font-mono text-xs text-text-muted">
              Computing explanation...
            </p>
          ) : null}

          {error ? (
            <p className="font-mono text-xs text-red-400">{error}</p>
          ) : null}

          {!loading && !error && data ? (
            <>
              <p className="font-mono text-xs text-text-secondary">
                {data.overall_summary}
              </p>
              {cards.length === 0 ? (
                <p className="font-mono text-2xs text-text-muted">
                  No scorecard available for this section.
                </p>
              ) : (
                cards.map((card) => (
                  <ScoreCardView key={card.score_key} card={card} />
                ))
              )}
            </>
          ) : null}
        </div>

        {data ? (
          <footer className="border-t border-border px-4 py-3">
            <p className="font-mono text-2xs italic text-text-muted">
              {data.disclaimer}
            </p>
          </footer>
        ) : null}
      </aside>
    </div>
  );
}
