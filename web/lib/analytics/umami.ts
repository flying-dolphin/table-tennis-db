/**
 * Umami 自建埋点封装
 *
 * Umami 的 tracker script 自带 SPA 自动 PV，但我们用 data-auto-track="false"
 * 关闭它，由组件监听 Next.js App Router 的路由变化手动上报，行为更可控。
 */

type UmamiPayload = Record<string, string | number | boolean>;

interface UmamiTracker {
  track: {
    (): void;
    (eventName: string): void;
    (eventName: string, data: UmamiPayload): void;
    (props: { url?: string; referrer?: string; title?: string; website?: string }): void;
  };
  identify: (data: UmamiPayload) => void;
}

declare global {
  interface Window {
    umami?: UmamiTracker;
    clarity?: (...args: unknown[]) => void;
  }
}

export const UMAMI_URL = process.env.NEXT_PUBLIC_UMAMI_URL;
export const UMAMI_WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;
export const CLARITY_PROJECT_ID = process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID;

export const isUmamiEnabled = (): boolean => Boolean(UMAMI_URL && UMAMI_WEBSITE_ID);
export const isClarityEnabled = (): boolean => Boolean(CLARITY_PROJECT_ID);

/** 上报页面浏览。url 为站内路径（如 /rankings?week=2026-12）。 */
export function trackPageview(url: string, referrer?: string): void {
  if (typeof window === 'undefined' || !window.umami) return;
  window.umami.track({ url, referrer: referrer ?? document.referrer ?? '' });
}

/**
 * 上报自定义事件。
 * @param name 事件名，如 'ranking_sort' / 'player_view'
 * @param data 事件附加数据，如 { method: 'by_winrate', slug: 'sun-yingsha' }
 */
export function trackEvent(name: string, data?: UmamiPayload): void {
  if (typeof window === 'undefined' || !window.umami) return;
  if (data) window.umami.track(name, data);
  else window.umami.track(name);
}

/** 给当前访客打标识（如登录用户邮箱哈希），便于 Clarity / Umami 关联会话 */
export function identify(data: UmamiPayload): void {
  if (typeof window === 'undefined') return;
  window.umami?.identify(data);
  if (window.clarity) {
    const id = String(data.userId ?? data.id ?? '');
    if (id) window.clarity('identify', id);
  }
}
