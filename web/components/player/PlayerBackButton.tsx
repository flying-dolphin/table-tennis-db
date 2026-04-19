"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

export function PlayerBackButton() {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.back()}
      className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-[12px] font-bold text-white/85 backdrop-blur-sm transition-colors hover:bg-white/15"
    >
      <ArrowLeft size={14} strokeWidth={2} />
      返回
    </button>
  );
}
