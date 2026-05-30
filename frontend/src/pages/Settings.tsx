import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";

export default function Settings() {
  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Workspace configuration. API keys, providers, and members arrive in later milestones."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card label="Workspace">
          <p className="text-sm text-text-secondary">Local Workspace</p>
          <p className="mt-1 text-xs text-text-muted">
            Single local organization and project (M1).
          </p>
        </Card>

        <Card label="Milestone">
          <p className="mono-num text-sm text-text-secondary">M1 · Foundation</p>
          <p className="mt-1 text-xs text-text-muted">
            Clean full-stack foundation. No product modules wired yet.
          </p>
        </Card>
      </div>
    </>
  );
}
