import type { Metadata } from 'next';
import { Suspense } from 'react';
import './globals.css';
import BottomNav from '@/components/BottomNav';
import { APP_NAME, APP_DESCRIPTION } from '@/lib/constants';

export const metadata: Metadata = {
  title: `${APP_NAME} · 女子单打`,
  description: APP_DESCRIPTION,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="pb-[calc(4rem+env(safe-area-inset-bottom))] text-text-primary min-h-screen antialiased font-body">
        {children}
        <Suspense fallback={null}>
          <BottomNav />
        </Suspense>
      </body>
    </html>
  );
}
