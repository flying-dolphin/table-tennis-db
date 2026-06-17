"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { getRankingAvatarSources } from "@/lib/avatar-paths";

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
  const displayName = player.nameZh?.trim() || player.name;

  const sources = getRankingAvatarSources(player.avatarFile);

  const [error, setError] = useState(!player.avatarFile);
  const [imgSrc, setImgSrc] = useState(sources.primary);
  const [fallbackIndex, setFallbackIndex] = useState(0);

  useEffect(() => {
    setError(!player.avatarFile);
    setImgSrc(sources.primary);
    setFallbackIndex(0);
  }, [player.avatarFile, sources.primary]);

  const handleImageError = () => {
    const fallback = sources.fallbacks[fallbackIndex];
    if (fallback) {
      setImgSrc(fallback);
      setFallbackIndex((current) => current + 1);
    } else if (imgSrc !== sources.default) {
      setImgSrc(sources.default);
    } else {
      setError(true);
    }
  };

  const sizeClasses = {
    sm: "w-9 h-9 text-xs",
    md: "w-12 h-12 text-lg",
    lg: "w-24 h-24 text-3xl",
  };

  const imageSizes = {
    sm: 36,
    md: 48,
    lg: 96,
  };

  const containerClasses = cn(
    "rounded-full flex items-center justify-center shrink-0 shadow-sm relative z-10 overflow-hidden",
    sizeClasses[size],
    className
  );

  const bgClasses = size === "sm"
    ? "bg-gradient-to-br from-[#8CA8C7] to-[#607D9E]"
    : "bg-gradient-to-br from-brand-primary to-brand-deep";

  if (!error && imgSrc) {
    return (
      <div className={cn(containerClasses, "bg-slate-50")}>
        <Image
          src={imgSrc}
          alt={player.name}
          width={imageSizes[size]}
          height={imageSizes[size]}
          sizes={`${imageSizes[size]}px`}
          className="w-full h-full object-cover"
          onError={handleImageError}
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
