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
          className="object-cover opacity-90"
          priority
        />
        {/* Softer gradient for better image visibility while maintaining text contrast */}
        <div className="absolute inset-0 bg-gradient-to-t from-[#1A232C]/80 via-black/10 to-transparent" />
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
        <div className="absolute top-6 right-6 w-12 h-12 rounded-full border border-white/30 overflow-hidden bg-white/10 backdrop-blur-sm shadow-lg transition-all duration-300 hover:scale-105">
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
