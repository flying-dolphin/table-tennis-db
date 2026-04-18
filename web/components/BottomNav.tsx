"use client";

import React from "react";
import { Home, Trophy, User } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const PingPongIcon = ({ size = 24, strokeWidth = 2, className, ...props }: any) => (
  <svg 
    width={size} height={size} viewBox="0 0 24 24" fill="none" 
    stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" 
    className={className} {...props}
  >
    <circle cx="9" cy="9" r="6" />
    <path d="m13.24 13.24 4.09 4.1a2 2 0 1 1-2.83 2.83l-4.1-4.09" />
    <path d="M19.5 5.5a2 2 0 1 1 0-4 2 2 0 0 1 0 4Z" />
  </svg>
);

export default function BottomNav() {
  const [activeTab, setActiveTab] = React.useState("home");

  const navItems = [
    { id: "home", label: "首页", icon: Home },
    { id: "ranking", label: "排名", icon: Trophy },
    { id: "events", label: "赛事", icon: PingPongIcon },
    { id: "profile", label: "我的", icon: User },
  ];

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 pointer-events-none pb-[env(safe-area-inset-bottom)]">
      <nav className="w-full bg-white/80 backdrop-blur-2xl py-2 px-6 flex items-center justify-around pointer-events-auto border-t border-white/60 shadow-[0_-10px_40px_rgba(0,0,0,0.03)]">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "relative flex flex-col items-center justify-center transition-all duration-300 h-14 min-w-[4.5rem] px-2 rounded-2xl",
                isActive ? "bg-[#123E7A] text-white shadow-md shadow-[#123E7A]/30 scale-105" : "text-[#1E2A3D] hover:bg-black/5"
              )}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 2} className="mb-1" />
              <span className="text-[11px] font-bold tracking-wide">
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
