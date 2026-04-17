import React from "react";
import Image from "next/image";

export default function Hero() {
  return (
    <section className="relative w-full h-[180px] overflow-hidden rounded-b-[40px] bg-[#1A232C] shadow-lg">
      {/* Background Image */}
      <div className="absolute inset-0">
        <Image
          src="/images/hero.jpg"
          alt="Athlete Hero"
          fill
          className="object-cover opacity-70"
          priority
        />
        {/* Strong top-to-bottom dark gradient strictly for text legibility, maintaining dark contrast */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#1A232C]/90 via-black/20 to-transparent" />
      </div>

      {/* Content */}
      <div className="relative z-10 h-full flex flex-col justify-end p-8 pb-8">
        <p className="text-white/70 text-[10px] font-bold tracking-widest mb-1 uppercase drop-shadow-md">
          ITTF & WTT Data Hub
        </p>
        <h1 className="text-white text-2xl font-black leading-tight tracking-tight drop-shadow-md">
          乒乓球<br />
          <span className="text-brand-soft">职业数据查询</span>
        </h1>
        
        {/* Profile Circle Mockup */}
        <div className="absolute top-8 right-8 w-12 h-12 rounded-full border-2 border-white/20 overflow-hidden bg-white/10 backdrop-blur-sm shadow-sm">
          <div className="w-full h-full flex items-center justify-center text-white font-bold">
            TT
          </div>
        </div>
      </div>
    </section>
  );
}
