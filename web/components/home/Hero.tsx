import React from "react";
import Image from "next/image";

export default function Hero() {
  return (
    <section className="relative w-full h-[160px] overflow-hidden bg-[rgb(var(--hero-anchor))] shadow-lg">
      {/* Background Image */}
      <div className="absolute inset-0">
        <Image
          src="/images/hero.jpg"
          alt="Athlete Hero"
          fill
          className="object-cover opacity-90"
          priority
        />
        {/* Softer gradient for better image visibility while maintaining text contrast */}
        <div className="absolute inset-0 bg-gradient-to-t from-[rgb(var(--hero-anchor))/0.8] via-black/10 to-transparent" />
      </div>

      {/* Content */}
      <div className="relative z-10 h-full flex flex-col justify-end p-5 pb-6">
        <div className="flex items-end gap-x-2">
          <h1 className="text-white text-display font-black tracking-tight drop-shadow-md font-heading">
            豆包球谱
          </h1>
          <p className="text-body font-bold text-white">女单版</p>
        </div>
        <p className="mt-1 text-body font-medium font-body text-white/78 tracking-[0.01em] drop-shadow-sm">
          国际赛事数据查询
        </p>

        {/* Profile Circle Mockup */}
        <div className="absolute top-4 right-4 w-12 h-12 rounded-full border border-white/30 overflow-hidden bg-white/10 backdrop-blur-sm shadow-lg transition-all duration-300 hover:scale-105">
          <Image
            src="/images/logo.png"
            alt="ITTF Logo"
            fill
            className="object-contain scale-195"
          />
        </div>
      </div>
    </section>
  );
}
