import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-[#E2ECF6] via-[#E9F1F8] to-[#EDF3F9] relative overflow-hidden">
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
