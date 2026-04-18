import React from "react";
import { Search } from "lucide-react";

export default function SearchBox() {
  return (
    <div className="relative -mt-6 px-6 z-20">
      <div className="flex items-center bg-white/95 rounded-[20px] h-14 px-5 gap-3 shadow-[0_20px_50px_-10px_rgba(40,65,105,0.12),inset_0_1px_4px_rgba(255,255,255,1)] border-[1.5px] border-white focus-within:shadow-[0_30px_60px_-15px_rgba(40,65,105,0.15)] transition-all duration-300">
        <Search className="text-brand-strong" size={22} />
        <input
          type="text"
          placeholder="试试：孙颖莎、王曼昱最近 3 年交手记录"
          className="flex-1 bg-transparent border-none outline-none text-text-primary placeholder:text-text-tertiary font-medium text-[13px] h-full"
        />
      </div>
    </div>
  );
}
