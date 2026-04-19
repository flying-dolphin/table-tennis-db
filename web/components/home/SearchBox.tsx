"use client";

import React from "react";
import { Search } from "lucide-react";

export default function SearchBox() {
  function handleClick() {
    window.location.href = "/auth";
  }

  return (
    <div className="relative -mt-4 px-6 z-20">
      <button
        type="button"
        onClick={handleClick}
        className="group w-full text-left"
        aria-label="登录后使用搜索"
      >
        <div className="flex items-center bg-white rounded-2xl h-14 px-5 gap-3 shadow-md border border-border-subtle transition-all duration-300 group-hover:shadow-lg">
          <Search className="text-brand-strong" size={22} />
          <input
            type="text"
            placeholder="试试：孙颖莎、王曼昱最近 3 年交手记录"
            className="flex-1 bg-transparent border-none outline-none text-text-primary placeholder:text-text-tertiary font-medium text-[13px] h-full cursor-pointer"
            disabled
            readOnly
          />
        </div>
      </button>
    </div>
  );
}
