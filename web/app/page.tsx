import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";

export default function HomePage() {
  return (
    <main className="relative flex flex-col gap-6 pb-8">
      <div className="relative">
        <Hero />
        <SearchBox />
      </div>

      <EventScroller />
      <RankingTable />
    </main>
  );
}
