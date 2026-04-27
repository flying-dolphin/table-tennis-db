import PlayerDetailPageClient from "@/components/player/PlayerDetailPageClient";
import { getPlayerDetail } from "@/lib/server/players";
import { notFound } from "next/navigation";

export default async function PlayerDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detail = getPlayerDetail(slug);

  if (!detail) {
    notFound();
  }

  return <PlayerDetailPageClient initialDetail={detail} />;
}
