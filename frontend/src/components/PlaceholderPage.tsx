import PageHeader from "./PageHeader";
import EmptyState from "./EmptyState";

interface PlaceholderPageProps {
  title: string;
  subtitle: string;
  tag?: string;
  emptyTitle: string;
  emptyDescription: string;
}

export default function PlaceholderPage({
  title,
  subtitle,
  tag,
  emptyTitle,
  emptyDescription,
}: PlaceholderPageProps) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} tag={tag} />
      <EmptyState title={emptyTitle} description={emptyDescription} />
    </>
  );
}
