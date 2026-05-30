import PlaceholderPage from "@/components/PlaceholderPage";

export default function Timeline() {
  return (
    <PlaceholderPage
      tag="Analysis"
      title="Audit Trail"
      subtitle="Chronological evidence log of every strategy change, run, assumption update, and detected anomaly."
      emptyTitle="No audit events"
      emptyDescription="Events are generated from underlying objects once strategies and runs are ingested. Timeline view arrives in a later milestone."
    />
  );
}
