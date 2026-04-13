"use client";

import React from "react";
import { Home, Trophy, Calendar, Briefcase } from "lucide-react";
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
    { id: "schedule", label: "日程", icon: Calendar },
    { id: "events", label: "赛事", icon: Briefcase },
  ];

  return (
    <nav className="pill-nav-container">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;
        
        return (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={cn(
              "nav-item flex-1 min-w-[64px]",
              isActive && "active"
            )}
          >
            <Icon size={22} className={cn("transition-transform duration-300", isActive && "scale-115")} />
            <span className="text-[10px] mt-1 font-medium tracking-wide">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
