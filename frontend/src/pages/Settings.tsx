import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";

export default function Settings() {
  return (
    <>
      <PageHeader
        tag="Config"
        title="Settings"
        subtitle="Workspace configuration. API keys, data providers, and team access arrive in later milestones."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card label="Workspace">
          <p className="text-sm text-text-secondary">Local Workspace</p>
          <p className="mt-1 font-mono text-2xs text-text-muted">
            Single local organization. Team and org management arrive later.
          </p>
        </Card>

        <Card label="Milestone">
          <p className="mono-num text-sm text-text-secondary">M5 · Run Comparison</p>
          <p className="mt-1 font-mono text-2xs text-text-muted">
            Deterministic run diffing — params, assumptions, metrics, and metadata.
          </p>
        </Card>
      </div>
    </>
  );
}
