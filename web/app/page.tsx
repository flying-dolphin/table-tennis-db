import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";

export default function HomePage() {
  return (
    <main className="relative overflow-hidden">
      {/* Hero Section */}
      <Hero />

      {/* Search Box - Overlays Hero */}
      <SearchBox />

      {/* Monthly Event Scroller */}
      <EventScroller />

      {/* Rankings List */}
      <RankingTable />
    </main>
  );
}
