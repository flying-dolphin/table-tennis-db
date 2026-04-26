"use client";

import React, { useCallback, useRef, useState } from "react";
import { Search } from "lucide-react";

export default function SearchBox() {
  const [query, setQuery] = useState("");
  const [authState, setAuthState] = useState<"unknown" | "authenticated" | "unauthenticated">("unknown");
  const [checkingAuth, setCheckingAuth] = useState(false);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const [showNotFoundPrompt, setShowNotFoundPrompt] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const placeholder = "搜索球员或赛事，例如：孙颖莎 或 澳门世界杯";

  const checkLoggedIn = useCallback(async (): Promise<boolean> => {
    if (authState === "authenticated") return true;
    if (authState === "unauthenticated") return false;
    if (checkingAuth) return false;

    setCheckingAuth(true);
    try {
      const response = await fetch("/api/v1/auth/me", {
        method: "GET",
        credentials: "include",
        cache: "no-store",
      });
      const ok = response.ok;
      setAuthState(ok ? "authenticated" : "unauthenticated");
      return ok;
    } catch {
      setAuthState("unauthenticated");
      return false;
    } finally {
      setCheckingAuth(false);
    }
  }, [authState, checkingAuth]);

  async function handleInputFocus() {
    if (authState === "unauthenticated") {
      inputRef.current?.blur();
      setShowLoginPrompt(true);
      return;
    }
    const isLoggedIn = await checkLoggedIn();
    if (!isLoggedIn) {
      inputRef.current?.blur();
      setShowLoginPrompt(true);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || isSearching) return;

    const isLoggedIn = await checkLoggedIn();
    if (!isLoggedIn) {
      setShowLoginPrompt(true);
      return;
    }

    setIsSearching(true);
    try {
      const playerRes = await fetch(`/api/v1/players/search?q=${encodeURIComponent(query.trim())}&limit=1`);
      if (playerRes.ok) {
        const payload = await playerRes.json();
        const items = payload.data?.items || [];
        if (items.length > 0) {
          window.location.href = `/players/${items[0].slug}`;
          return;
        }
      }

      const eventRes = await fetch(`/api/v1/events?q=${encodeURIComponent(query.trim())}&limit=1`);
      if (eventRes.ok) {
        const payload = await eventRes.json();
        const events = payload.data?.events || [];
        if (events.length > 0) {
          window.location.href = `/events/${events[0].eventId}`;
          return;
        }
      }

      setShowNotFoundPrompt(true);
    } catch (e) {
      console.error("Search failed:", e);
      setShowNotFoundPrompt(true);
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="relative -mt-4 px-5 z-20">
      <form className="group w-full" onSubmit={handleSubmit}>
        <div className="flex items-center bg-white rounded-md h-14 px-5 gap-3 shadow-md border border-border-subtle transition-all duration-300 group-hover:shadow-lg">
          <Search className="text-brand-strong" size={22} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={handleInputFocus}
            placeholder={placeholder}
            className="flex-1 bg-transparent border-none outline-none text-text-primary placeholder:text-text-tertiary font-medium text-body h-full disabled:opacity-50"
            aria-label="搜索问题输入框"
            disabled={isSearching}
          />
          <button
            type="submit"
            disabled={isSearching}
            className="shrink-0 px-2 py-1 text-caption font-medium text-brand-deep hover:text-brand-strong transition-colors disabled:opacity-50"
          >
            {isSearching ? "搜索中" : "搜索"}
          </button>
        </div>
      </form>

      {showLoginPrompt && (
        <div className="fixed inset-0 z-[70] bg-[rgb(var(--overlay-dark))/0.35] backdrop-blur-sm flex items-center justify-center px-5">
          <div className="w-full max-w-[320px] rounded-lg bg-white border border-border-subtle shadow-xl p-5">
            <h3 className="text-heading-2 font-bold text-text-primary">登录后可用搜索</h3>
            <p className="mt-2 text-body text-text-secondary leading-relaxed">
              当前搜索功能需要登录后使用。是否前往登录页？
            </p>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowLoginPrompt(false)}
                className="px-3 py-1.5 rounded-sm text-body font-medium text-text-secondary hover:bg-surface-secondary transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowLoginPrompt(false);
                  window.location.href = "/auth";
                }}
                className="px-3 py-1.5 rounded-sm text-body font-semibold text-white bg-brand-deep hover:bg-brand-strong transition-colors"
              >
                去登录
              </button>
            </div>
          </div>
        </div>
      )}

      {showNotFoundPrompt && (
        <div className="fixed inset-0 z-[70] bg-[rgb(var(--overlay-dark))/0.35] backdrop-blur-sm flex items-center justify-center px-5">
          <div className="w-full max-w-[320px] rounded-lg bg-white border border-border-subtle shadow-xl p-5">
            <h3 className="text-heading-2 font-bold text-text-primary">未找到结果</h3>
            <p className="mt-2 text-body text-text-secondary leading-relaxed">
              目前仅支持人名和赛事搜索，未找到匹配的结果，请换个词试试。
            </p>
            <div className="mt-4 flex items-center justify-end">
              <button
                type="button"
                onClick={() => setShowNotFoundPrompt(false)}
                className="px-3 py-1.5 rounded-sm text-body font-semibold text-white bg-brand-deep hover:bg-brand-strong transition-colors"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
