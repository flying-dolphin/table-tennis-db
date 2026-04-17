"use client";

import React from "react";
import { Home, Trophy, Swords, User } from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function BottomNav() {
  const [activeTab, setActiveTab] = React.useState("home");

  const navItems = [
    { id: "home", label: "首页", icon: Home },
    { id: "ranking", label: "排名", icon: Trophy },
    { id: "events", label: "赛事", icon: Swords },
    { id: "profile", label: "我的", icon: User },
  ];

  return (
    <div className="fixed bottom-6 left-0 right-0 z-50 px-8 pointer-events-none">
      <nav className="max-w-md mx-auto bg-white/95 backdrop-blur-md shadow-[0_20px_40px_rgba(0,0,0,0.08)] py-2.5 px-3 rounded-full flex items-center justify-between pointer-events-auto border border-white/50">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "relative shrink-0 flex items-center justify-center rounded-full transition-all duration-500 overflow-hidden",
                isActive 
                  ? "w-14 h-14 bg-brand-deep text-white shadow-lg shadow-brand-deep/30" 
                  : "w-14 h-14 text-text-tertiary hover:bg-surface-secondary"
              )}
            >
              <div className={cn("relative z-10 transition-transform duration-300", isActive && "scale-110")}>
                <Icon size={24} strokeWidth={isActive ? 2.5 : 2} />
              </div>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
