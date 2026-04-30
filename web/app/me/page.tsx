"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, LogOut } from "lucide-react";

interface UserInfo {
  user_id: number;
  username: string;
  email: string;
  created_at: string;
}

export default function MePage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  const router = useRouter();

  useEffect(() => {
    fetch("/api/v1/auth/me", { credentials: "include", cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data: { data: UserInfo }) => setUser(data.data))
      .catch(() => router.replace("/auth"))
      .finally(() => setLoading(false));
  }, [router]);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" }).catch(() => {});
    window.location.href = "/";
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-surface-secondary flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-brand-deep border-t-transparent rounded-full animate-spin" />
      </main>
    );
  }

  if (!user) return null;

  const joinDate = new Date(user.created_at).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const initial = user.username[0].toUpperCase();

  return (
    <main className="min-h-screen bg-surface-secondary flex flex-col">
      <div className="flex items-center px-4 pt-safe pt-4 pb-2">
        <Link
          href="/"
          className="flex items-center gap-1 text-text-secondary hover:text-text-primary transition-colors"
        >
          <ChevronLeft size={18} />
          <span className="text-body">首页</span>
        </Link>
      </div>

      <div className="flex-1 flex flex-col items-center px-5 pt-6 pb-24">
        <div className="w-full max-w-sm">
          {/* Avatar */}
          <div className="flex flex-col items-center mb-7">
            <div className="w-20 h-20 rounded-full bg-brand-mist border-2 border-brand-soft flex items-center justify-center mb-3">
              <span className="text-heading-1 font-bold text-brand-deep">{initial}</span>
            </div>
            <h1 className="text-heading-1 font-bold text-text-primary">{user.username}</h1>
            <p className="mt-1 text-body text-text-secondary">{user.email}</p>
          </div>

          {/* Info card */}
          <div className="bg-white rounded-md border border-border-subtle shadow-sm overflow-hidden mb-4">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
              <span className="text-body text-text-secondary">用户名</span>
              <span className="text-body font-medium text-text-primary">{user.username}</span>
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
              <span className="text-body text-text-secondary">邮箱</span>
              <span className="text-body font-medium text-text-primary break-all text-right ml-4">
                {user.email}
              </span>
            </div>
            <div className="flex items-center justify-between px-4 py-3">
              <span className="text-body text-text-secondary">注册时间</span>
              <span className="text-body font-medium text-text-primary">{joinDate}</span>
            </div>
          </div>

          {/* Logout */}
          <button
            type="button"
            onClick={handleLogout}
            disabled={loggingOut}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-md border border-border-subtle bg-white text-body font-medium text-state-danger hover:bg-state-danger/5 transition-colors disabled:opacity-60"
          >
            <LogOut size={18} />
            {loggingOut ? "退出中…" : "退出登录"}
          </button>
        </div>
      </div>
    </main>
  );
}
