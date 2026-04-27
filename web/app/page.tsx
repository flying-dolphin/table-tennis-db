import Hero from "@/components/home/Hero";
import SearchBox from "@/components/home/SearchBox";
import EventScroller from "@/components/home/EventScroller";
import RankingTable from "@/components/home/RankingTable";
import DataDisclaimer from "@/components/home/DataDisclaimer";

export default function HomePage() {
  return (
    <main className="relative flex flex-col gap-2 pb-8">
      <div className="relative">
        <Hero />
        <SearchBox />
      </div>

      <EventScroller />
      <DataDisclaimer />
      <RankingTable />
    </main>
  );
}
