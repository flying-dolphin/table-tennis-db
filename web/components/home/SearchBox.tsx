import React from "react";
import { Search, SlidersHorizontal } from "lucide-react";

export default function SearchBox() {
  return (
    <div className="relative -mt-6 px-4 z-20">
      <div className="bg-surface-primary rounded-[24px] p-2 shadow-sm border border-border-subtle">
        <div className="flex items-center bg-page-background rounded-[16px] h-14 px-4 gap-3 focus-within:ring-2 focus-within:ring-brand-primary/20 transition-all">
          <Search className="text-brand-deep" size={20} />
          <input
            type="text"
            placeholder="试试：孙颖莎、王曼昱最近 3 年交手记录"
            className="flex-1 bg-transparent border-none outline-none text-text-primary placeholder:text-text-tertiary font-medium text-[13px] h-full"
          />
        </div>
      </div>
    </div>
  );
}
