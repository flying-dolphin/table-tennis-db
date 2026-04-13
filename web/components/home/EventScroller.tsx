"use client";

import React, { useState } from "react";
import { MOCK_MONTHS } from "@/lib/mock";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import CalendarModal from "./CalendarModal";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function EventScroller() {
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);

  return (
    <section className="mt-8">
      <div className="px-8 flex justify-between items-end mb-4">
        <h2 className="text-xl font-bold">Upcoming Events</h2>
        <button className="text-sm font-medium text-dark/40 hover:text-dark transition-colors">
          View all
        </button>
      </div>

      <div className="flex overflow-x-auto gap-4 px-8 pb-4 no-scrollbar">
        {MOCK_MONTHS.map((month, index) => (
          <div
            key={month.id}
            onClick={() => setSelectedMonth(month.id)}
            className={cn(
              "flex-shrink-0 cursor-pointer transition-all duration-300",
              month.active ? "w-64" : "w-48"
            )}
          >
            <div
              className={cn(
                "h-64 rounded-[32px] p-8 flex flex-col justify-between transition-all duration-500",
                month.active
                  ? "bg-dark text-white shadow-xl shadow-dark/20"
                  : "bg-white text-dark shadow-sm border border-dark/5"
              )}
            >
              <div>
                <div
                  className={cn(
                    "w-12 h-12 rounded-2xl flex items-center justify-center mb-4 transition-colors",
                    month.active ? "bg-white/10" : "bg-dark/5"
                  )}
                >
                  <span className="text-xl">📅</span>
                </div>
                <h3 className="text-2xl font-bold leading-tight">
                  {month.name_zh}<br />
                  <span className={cn("text-lg font-normal opacity-60", month.active && "text-mint")}>
                    {month.name}
                  </span>
                </h3>
              </div>

              <div className="flex items-center gap-2">
                <span className={cn("text-sm font-medium", month.active ? "text-mint" : "text-dark/40")}>
                  {month.active ? "Current Selection" : "Tap to view"}
                </span>
                <div className={cn("flex-1 h-px", month.active ? "bg-white/10" : "bg-dark/5")} />
                <div className={cn("w-8 h-8 rounded-full flex items-center justify-center transition-colors", month.active ? "bg-mint text-dark" : "bg-dark/5 text-dark/40")}>
                  →
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {selectedMonth && (
        <CalendarModal
          monthId={selectedMonth}
          onClose={() => setSelectedMonth(null)}
        />
      )}
    </section>
  );
}
