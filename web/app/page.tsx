import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-[#DDEAF6] via-[#E5EEF7] to-[#F0F6FB] relative overflow-hidden">
      {/* Pure Blue & White Ambient Lighting */}
      <div className="absolute top-[5%] right-[-10%] w-[70vw] h-[70vw] bg-white/90 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute top-[40%] left-[-20%] w-[60vw] h-[60vw] bg-[#6B97CB]/20 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[5%] right-[10%] w-[50vw] h-[50vw] bg-[#4F79B3]/15 rounded-full blur-[90px] pointer-events-none" />

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
