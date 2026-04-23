"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Home, Trophy, User } from "lucide-react";
import { IconPingPong } from "@tabler/icons-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const EventsIcon = ({ size = 24, strokeWidth = 1.5, ...props }: any) => (
  <IconPingPong size={size} stroke={strokeWidth} {...props} />
);

export default function BottomNav() {
  const pathname = usePathname();

  const navItems: Array<{ id: string; label: string; href: Route; icon: React.ComponentType<any> }> = [
    { id: "home", label: "首页", href: "/", icon: Home },
    { id: "ranking", label: "排名", href: "/rankings", icon: Trophy },
    { id: "events", label: "赛事", href: "/events", icon: EventsIcon },
    { id: "profile", label: "我的", href: "/auth", icon: User },
  ];

  const routeIndex = navItems.findIndex((item) =>
    item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`)
  );

  const [activeIndex, setActiveIndex] = useState(routeIndex);

  useEffect(() => {
    if (routeIndex >= 0) setActiveIndex(routeIndex);
  }, [routeIndex]);

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 bg-white/80 backdrop-blur-xl border-t border-black/5"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="relative flex items-center justify-around h-16 max-w-[430px] mx-auto">
        {navItems.map((item, index) => {
          const Icon = item.icon;
          const isActive = index === activeIndex;

          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={(event) => {
                const isHomeTapOnHome = item.href === "/" && pathname === "/";
                if (isHomeTapOnHome) {
                  event.preventDefault();
                }
                setActiveIndex(index);
              }}
              className="relative flex flex-col items-center justify-center gap-1 flex-1 h-full select-none transition-transform duration-150 ease-out active:scale-[0.88]"
            >
              <Icon
                size={24}
                strokeWidth={1.5}
                className={cn(
                  "transition-colors duration-200",
                  isActive ? "text-brand-deep" : "text-text-tertiary"
                )}
              />
              <span
                className={cn(
                  "text-[10px] font-medium tracking-wide transition-colors duration-200",
                  isActive ? "text-brand-deep" : "text-text-tertiary"
                )}
              >
                {item.label}
              </span>
            </Link>
          );
        })}

        <motion.div
          className="pointer-events-none absolute bottom-1 left-0 flex justify-center"
          style={{ width: `${100 / navItems.length}%` }}
          initial={false}
          animate={{
            x: `${Math.max(activeIndex, 0) * 100}%`,
            opacity: activeIndex >= 0 ? 1 : 0,
          }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          <span className="h-1 w-1 rounded-full bg-brand-deep" />
        </motion.div>
      </div>
    </nav>
  );
}
