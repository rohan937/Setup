import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import ScoreCard from "@/components/ScoreCard";
import EmptyState from "@/components/EmptyState";

const scoreCards = [
  "Data Health",
  "Backtest Trust",
  "Live Drift",
  "Execution Quality",
];

export default function Dashboard() {
  return (
    <>
      <PageHeader
        title="Strategy Reliability"
        subtitle="Where alpha breaks between data, backtests, production, and execution."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card label="Overall Reliability" className="lg:col-span-1">
          <p className="mono-num text-5xl font-semibold text-text-muted">—</p>
          <p className="mt-3 text-sm text-text-secondary">
            Computed from data health, backtest trust, live drift, and execution
            quality once strategies are instrumented.
          </p>
        </Card>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-2">
          {scoreCards.map((label) => (
            <ScoreCard key={label} label={label} />
          ))}
        </div>
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-base font-semibold text-text-primary">
          Strategies
        </h2>
        <EmptyState
          title="No strategies yet"
          description="Once you log a strategy run from the SDK or API, its lineage, scores, and diagnosis appear here. The SDK and ingestion arrive in a later milestone."
        />
      </div>
    </>
  );
}
