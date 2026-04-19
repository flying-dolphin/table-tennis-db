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
                "flex flex-col items-center justify-center gap-1 min-w-[58px] px-1 py-1 rounded-2xl transition-all duration-300",
                isActive ? "text-brand-deep" : "text-text-tertiary hover:text-text-secondary"
              )}
            >
              <div className={cn(
                "p-1 rounded-xl transition-all duration-300",
                isActive ? "bg-brand-soft/85 scale-105 shadow-inner" : "bg-transparent"
              )}>
                <Icon size={22} strokeWidth={isActive ? 2.5 : 2} />
              </div>
              <span className={cn(
                "text-[10px] font-bold tracking-tight transition-all duration-300",
                isActive ? "text-brand-deep scale-105" : "text-text-tertiary"
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
