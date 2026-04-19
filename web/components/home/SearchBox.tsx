"use client";

import React, { useRef, useState } from "react";
import { Search } from "lucide-react";

export default function SearchBox() {
  const [query, setQuery] = useState("");
  const [authState, setAuthState] = useState<"unknown" | "authenticated" | "unauthenticated">("unknown");
  const [checkingAuth, setCheckingAuth] = useState(false);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const placeholder = "试试：孙颖莎、王曼昱最近 3 年交手记录";

  async function checkLoggedIn(): Promise<boolean> {
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
  }

  async function handleInputFocus() {
    if (authState === "authenticated") return;
    const isLoggedIn = await checkLoggedIn();
    if (!isLoggedIn) {
      inputRef.current?.blur();
      setShowLoginPrompt(true);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const isLoggedIn = await checkLoggedIn();
    if (!isLoggedIn) {
      setShowLoginPrompt(true);
      return;
    }

    const finalQuery = query.trim() || placeholder;
    window.location.href = `/search?q=${encodeURIComponent(finalQuery)}`;
  }

  return (
    <div className="relative -mt-4 px-6 z-20">
      <form className="group w-full" onSubmit={handleSubmit}>
        <div className="flex items-center bg-white rounded-2xl h-14 px-5 gap-3 shadow-md border border-border-subtle transition-all duration-300 group-hover:shadow-lg">
          <Search className="text-brand-strong" size={22} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={handleInputFocus}
            placeholder={placeholder}
            className="flex-1 bg-transparent border-none outline-none text-text-primary placeholder:text-text-tertiary font-medium text-[13px] h-full"
            aria-label="搜索问题输入框"
          />
          <button
            type="submit"
            className="shrink-0 px-2 py-1 text-[12px] font-medium text-brand-deep hover:text-brand-strong transition-colors"
          >
            搜索
          </button>
        </div>
      </form>

      {showLoginPrompt && (
        <div className="fixed inset-0 z-[70] bg-[rgb(var(--overlay-dark))/0.35] backdrop-blur-sm flex items-center justify-center px-6">
          <div className="w-full max-w-[320px] rounded-3xl bg-white border border-border-subtle shadow-xl p-5">
            <h3 className="text-[16px] font-bold text-text-primary">登录后可用搜索</h3>
            <p className="mt-2 text-[13px] text-text-secondary leading-relaxed">
              当前搜索功能需要登录后使用。是否前往登录页？
            </p>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowLoginPrompt(false)}
                className="px-3 py-1.5 rounded-xl text-[13px] font-medium text-text-secondary hover:bg-surface-secondary transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowLoginPrompt(false);
                  window.location.href = "/auth";
                }}
                className="px-3 py-1.5 rounded-xl text-[13px] font-semibold text-white bg-brand-deep hover:bg-brand-strong transition-colors"
              >
                去登录
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
