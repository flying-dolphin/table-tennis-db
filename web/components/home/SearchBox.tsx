import React from "react";
import { Search, SlidersHorizontal } from "lucide-react";

export default function SearchBox() {
  return (
    <div className="relative -mt-8 px-4 z-20">
      <div className="flex items-center bg-white rounded-full h-16 px-6 shadow-lg shadow-black/5 gap-3">
        <Search className="text-dark/30" size={22} />
        <input
          type="text"
          placeholder="Search items..."
          className="flex-1 bg-transparent border-none outline-none text-dark placeholder:text-dark/30 font-medium"
        />
        <button className="w-10 h-10 rounded-xl bg-dark flex items-center justify-center text-white transition-transform active:scale-90">
          <SlidersHorizontal size={20} />
        </button>
      </div>
    </div>
  );
}
