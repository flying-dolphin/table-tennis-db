import React from "react";
import Image from "next/image";
import { Trophy, Medal } from "lucide-react";

export function getEventCategory(event: {
  eventSeries?: string | null;
  categoryNameZh?: string | null;
  name?: string | null;
  eventNameZh?: string | null;
  eventName?: string | null;
}) {
  const series = (event.eventSeries ?? "").trim().toUpperCase();
  const title = (
    event.categoryNameZh ||
    event.eventNameZh ||
    event.name ||
    event.eventName ||
    ""
  ).toUpperCase();

  if (series.includes("OLYMPIC") || title.includes("OLYMPIC") || title.includes("奥运")) {
    return "OLYMPIC";
  }

  if (
    title.includes("WORLD CHAMPIONSHIPS") ||
    title.includes("世界乒乓球锦标赛") ||
    title.includes("WORLD CUP") ||
    title.includes("世界杯")
  ) {
    return "MAJOR";
  }

  if (series === "WTT" || title.includes("WTT")) return "WTT";
  return "OTHER";
}

export function EventSeriesIcon({ category }: { category: string }) {
  if (category === "WTT") {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="8" r="6"></circle>
        <path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"></path>
      </svg>
    );
  }
  if (category === "MAJOR") {
    return <Trophy size={20} strokeWidth={2} />;
  }
  if (category === "OLYMPIC") {
    return (
      <div className="relative h-7 w-7">
        <Image src="/icons/Olympic.svg" alt="Olympics" fill className="object-contain" />
      </div>
    );
  }
  return <Medal size={20} strokeWidth={2} />;
}

export function EventCategoryIcon({ category, className = "" }: { category: string; className?: string }) {
  let containerColorClass = "bg-silver text-white";

  if (category === "WTT") {
    containerColorClass = "bg-brand-strong text-white";
  } else if (category === "MAJOR") {
    containerColorClass = "bg-gold text-white";
  } else if (category === "OLYMPIC") {
    containerColorClass = "bg-white border border-black/[0.04] shadow-sm text-text-primary";
  }

  return (
    <div className={`grid place-items-center shrink-0 ${containerColorClass} ${className}`}>
      <EventSeriesIcon category={category} />
    </div>
  );
}
