import React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

const ShieldChartIcon = ({ className }: { className?: string }) => (
  <svg
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M16 2.66663L3.99996 7.99996V14.6666C3.99996 21.3999 9.15996 27.68 16 29.3333C22.84 27.68 28 21.3999 28 14.6666V7.99996L16 2.66663Z"
      fill="#EBF5FF"
      stroke="#3B82F6"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M10.6666 18.6667L14.6666 13.3333L18.6666 17.3333L22.6666 12"
      stroke="#3B82F6"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M22.6666 12V16M22.6666 12H18.6666"
      stroke="#3B82F6"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export default function DataDisclaimer() {
  return (
    <section className="px-5">
      <div className="px-3 py-1.5 bg-gradient-to-r from-[#F4F9FF] to-[#E8F3FF] border border-brand-primary border-dashed rounded-sm flex items-center gap-3">
        <div className="shrink-0 pl-1">
          <ShieldChartIcon className="w-4 h-4" />
        </div>
        <div className="flex-1 space-y-0.5">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-[#1C2024] text-sm">数据统计说明</h3>
            <Link href="/docs/data-explanation" className="flex items-center text-[13px] text-[#3B82F6] hover:text-blue-600 font-medium pb-px">
              查看详情
              <ChevronRight className="w-3 h-3 ml-0.5" strokeWidth={2.5} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
