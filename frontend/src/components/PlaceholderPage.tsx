import PageHeader from "./PageHeader";
import EmptyState from "./EmptyState";

interface PlaceholderPageProps {
  title: string;
  subtitle: string;
  emptyTitle: string;
  emptyDescription: string;
}

export default function PlaceholderPage({
  title,
  subtitle,
  emptyTitle,
  emptyDescription,
}: PlaceholderPageProps) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <EmptyState title={emptyTitle} description={emptyDescription} />
    </>
  );
}
