import RankingsPageClient from "@/components/rankings/RankingsPageClient";
import { getRankings } from "@/lib/server/rankings";

export default function RankingsPage() {
  const initialData = getRankings("women_singles", "points", 20, 0);

  return (
    <RankingsPageClient
      initialPlayers={initialData.players}
      initialHasMore={initialData.hasMore}
      initialRankingDate={initialData.snapshot?.rankingDate ?? null}
      initialSortBy="points"
    />
  );
}
