import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";
import { getHomeCalendar, getHomeRankings } from "@/lib/server/home";
import type { CalendarEvent } from "@/components/home/EventScroller";
import type { HomeRankingPlayer } from "@/components/home/RankingTable";

export default function HomePage() {
  const calendar = getHomeCalendar();
  const rankings = getHomeRankings(10, "women_singles");
  const initialEvents = calendar.events as CalendarEvent[];
  const initialPlayers = rankings.players as HomeRankingPlayer[];

  return (
    <main className="relative flex flex-col gap-6 pb-8">
      <div className="relative">
        <Hero />
        <SearchBox />
      </div>

      <EventScroller initialEvents={initialEvents} />
      <RankingTable initialPlayers={initialPlayers} />
    </main>
  );
}
