"use client";

import React, { useState } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type PlayerAvatarProps = {
  player: {
    playerId: number | string;
    name: string;
    nameZh?: string | null;
    avatarFile?: string | null;
  };
  size?: "sm" | "md" | "lg";
  className?: string;
};

export function PlayerAvatar({ player, size = "md", className }: PlayerAvatarProps) {
  const [error, setError] = useState(false);

  const displayName = player.nameZh?.trim() || player.name;
  
  // Use avatarFile if available, otherwise construct from name/id
  const filename = player.avatarFile || `player_${player.playerId}_${player.name.replace(/ /g, "_")}.png`;
  const avatarPath = `/images/avatars/${filename}`;

  const sizeClasses = {
    sm: "w-9 h-9 text-xs",
    md: "w-12 h-12 text-lg",
    lg: "w-24 h-24 text-3xl",
  };

  const containerClasses = cn(
    "rounded-full flex items-center justify-center shrink-0 shadow-sm border border-white relative z-10 overflow-hidden",
    sizeClasses[size],
    className
  );

  const bgClasses = size === "sm"
    ? "bg-gradient-to-br from-[#8CA8C7] to-[#607D9E]"
    : "bg-gradient-to-br from-brand-primary to-brand-deep";

  if (!error) {
    return (
      <div className={cn(containerClasses, "bg-slate-50")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={avatarPath}
          alt={player.name}
          className="w-full h-full object-cover"
          onError={() => setError(true)}
        />
      </div>
    );
  }

  return (
    <div className={cn(containerClasses, bgClasses)}>
      <span className="text-white font-medium tracking-widest leading-none drop-shadow-sm">
        {displayName.slice(0, 1)}
      </span>
    </div>
  );
}
