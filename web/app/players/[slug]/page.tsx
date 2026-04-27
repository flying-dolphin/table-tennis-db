import PlayerDetailPageClient from "@/components/player/PlayerDetailPageClient";

export default async function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <PlayerDetailPageClient slug={slug} />;
}
