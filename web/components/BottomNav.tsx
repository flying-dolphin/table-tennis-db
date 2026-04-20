"use client";

import React from "react";
import { usePathname } from "next/navigation";
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
  const pathname = usePathname();

  const navItems = [
    { id: "home", label: "首页", href: "/", icon: Home },
    { id: "ranking", label: "排名", href: "/rankings", icon: Trophy },
    { id: "events", label: "赛事", href: "/events", icon: PingPongIcon },
    { id: "profile", label: "我的", href: "/auth", icon: User },
  ];

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 pointer-events-none">
      <nav className="pill-nav-container pointer-events-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`);

          return (
            <a
              key={item.id}
              href={item.href}
              className={cn(
                "flex flex-col items-center justify-center gap-1.5 min-w-[64px] px-2 py-1.5 rounded-full transition-all duration-500 relative",
                isActive ? "text-brand-deep" : "text-text-tertiary hover:text-text-secondary"
              )}
            >
              {isActive && (
                <div className="absolute inset-0 bg-white/60 backdrop-blur-md rounded-full shadow-sm border border-white/80 -z-10 animate-in fade-in zoom-in-95 duration-500" />
              )}
              <div className={cn(
                "transition-all duration-500",
                isActive ? "scale-110 drop-shadow-[0_0_8px_rgba(26,35,44,0.15)]" : "bg-transparent"
              )}>
                <Icon size={20} strokeWidth={isActive ? 2.5 : 2} />
              </div>
              <span className={cn(
                "text-[10px] font-black tracking-widest transition-all duration-500 uppercase",
                isActive ? "" : "text-text-tertiary/80"
              )}>
                {item.label}
              </span>
            </a>
          );
        })}
      </nav>
    </div>
  );
}
