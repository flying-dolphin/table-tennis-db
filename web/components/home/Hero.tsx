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
      <div className="relative z-10 h-full flex flex-col justify-end p-6 pb-6">
        <p className="text-white/70 text-[10px] font-bold tracking-widest mb-1 uppercase drop-shadow-md">
          Data from ITTF & WTT
        </p>
        <h1 className="text-white text-[30px] font-black leading-[1.05] tracking-tight drop-shadow-md font-heading">
          豆包球谱
        </h1>
        <p className="mt-1 text-[13px] leading-[1.25] font-medium font-body text-white/78 tracking-[0.01em] drop-shadow-sm">
          国际赛事数据查询
        </p>

        {/* Profile Circle Mockup */}
        <div className="absolute top-4 right-4 w-12 h-12 rounded-full border border-white/30 overflow-hidden bg-white/10 backdrop-blur-sm shadow-lg transition-all duration-300 hover:scale-105">
          <Image
            src="/images/logo.png"
            alt="ITTF Logo"
            fill
            className="object-contain scale-190"
          />
        </div>
      </div>
    </section>
  );
}
