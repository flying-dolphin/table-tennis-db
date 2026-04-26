'use client';

import * as Sentry from '@sentry/nextjs';
import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="zh-CN">
      <body>
        <div style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
          <h1>出错了</h1>
          <p>页面遇到异常，已自动上报。</p>
          <button onClick={reset} style={{ marginTop: '1rem' }}>
            重试
          </button>
        </div>
      </body>
    </html>
  );
}
