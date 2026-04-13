import React from "react";
import Image from "next/image";

export default function Hero() {
  return (
    <section className="relative w-full h-[280px] overflow-hidden rounded-b-[40px] bg-dark">
      {/* Background Image */}
      <div className="absolute inset-0">
        <Image
          src="/images/hero.jpg"
          alt="Athlete Hero"
          fill
          className="object-cover opacity-80"
          priority
        />
        <div className="hero-gradient-overlay" />
      </div>

      {/* Content */}
      <div className="relative z-10 h-full flex flex-col justify-end p-8 pb-12">
        <p className="text-white/70 text-sm font-medium tracking-wide mb-1 uppercase">
          Welcome back
        </p>
        <h1 className="text-white text-3xl font-bold leading-tight">
          Let's find your<br />
          <span className="text-mint">Best Ranking</span>
        </h1>
        
        {/* Profile Circle Mockup */}
        <div className="absolute top-8 right-8 w-12 h-12 rounded-full border-2 border-mint/30 overflow-hidden bg-white/10 backdrop-blur-sm">
          <div className="w-full h-full flex items-center justify-center text-mint font-bold">
            TT
          </div>
        </div>
      </div>
    </section>
  );
}
