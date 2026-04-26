'use client';

import Script from 'next/script';
import { useEffect, useRef } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import {
  CLARITY_PROJECT_ID,
  UMAMI_URL,
  UMAMI_WEBSITE_ID,
  isClarityEnabled,
  isUmamiEnabled,
  trackEvent,
  trackPageview,
} from '@/lib/analytics/umami';

const MAX_LABEL_LEN = 60;

function describeElement(el: HTMLElement): { name: string; data: Record<string, string> } {
  // 优先使用 data-track / data-track-label 显式声明
  const explicitName = el.getAttribute('data-track');
  if (explicitName) {
    const label =
      el.getAttribute('data-track-label') ||
      el.getAttribute('aria-label') ||
      el.textContent?.trim() ||
      '';
    return { name: explicitName, data: { label: label.slice(0, MAX_LABEL_LEN) } };
  }

  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute('role');
  const ariaLabel = el.getAttribute('aria-label');
  const href = el.getAttribute('href');

  let name: string;
  if (tag === 'a' && href) name = href.startsWith('/') ? 'click_link_internal' : 'click_link_external';
  else if (tag === 'button') name = 'click_button';
  else if (role) name = `click_${role}`;
  else name = `click_${tag}`;

  const label = (ariaLabel || el.getAttribute('title') || el.textContent?.trim() || href || '').slice(
    0,
    MAX_LABEL_LEN,
  );

  const data: Record<string, string> = {};
  if (label) data.label = label;
  if (href) data.href = href.slice(0, 200);

  return { name, data };
}

export default function Analytics() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const prevUrlRef = useRef<string | null>(null);

  // 路由变化 → 上报 PV（Umami SDK 已关闭自动 PV）
  useEffect(() => {
    if (!isUmamiEnabled() || !pathname) return;
    const qs = searchParams?.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    trackPageview(url, prevUrlRef.current ?? undefined);
    prevUrlRef.current = url;
  }, [pathname, searchParams]);

  // 全站点击代理：只统计可交互元素
  useEffect(() => {
    if (!isUmamiEnabled()) return;

    const handler = (e: MouseEvent) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      const interactive = target.closest<HTMLElement>(
        'a, button, [role="button"], [role="link"], [role="tab"], [data-track]',
      );
      if (!interactive) return;
      if (interactive.hasAttribute('data-track-ignore')) return;

      const { name, data } = describeElement(interactive);
      trackEvent(name, data);
    };

    document.addEventListener('click', handler, { capture: true, passive: true });
    return () => document.removeEventListener('click', handler, { capture: true });
  }, []);

  return (
    <>
      {isUmamiEnabled() && (
        <Script
          src={`${UMAMI_URL}/script.js`}
          data-website-id={UMAMI_WEBSITE_ID}
          data-auto-track="false"
          strategy="afterInteractive"
        />
      )}
      {isClarityEnabled() && (
        <Script
          src={`https://www.clarity.ms/tag/${CLARITY_PROJECT_ID}`}
          strategy="afterInteractive"
        />
      )}
    </>
  );
}
