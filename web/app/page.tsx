import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-page-background">
      {/* Hero Section */}
      <Hero />
      
      {/* Search Box - Overlays Hero */}
      <SearchBox />

      {/* Monthly Event Scroller */}
      <EventScroller />

      {/* Rankings List */}
      <RankingTable />
      
      {/* Bottom Padding for Floating Nav */}
      <div className="h-24" />
    </main>
  );
}
