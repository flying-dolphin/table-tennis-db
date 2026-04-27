import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Noto_Sans_SC, Inter } from 'next/font/google';
import 'flag-icons/css/flag-icons.min.css';
import './globals.css';
import BottomNav from '@/components/BottomNav';
import Analytics from '@/components/Analytics';
import { APP_NAME, APP_DESCRIPTION } from '@/lib/constants';

const notoSansSC = Noto_Sans_SC({
  subsets: ['latin'],
  weight: ['300', '400', '500', '700', '900'],
  variable: '--font-noto-sans-sc',
  display: 'swap',
});

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '600', '700'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: `${APP_NAME}`,
  description: APP_DESCRIPTION,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={`${notoSansSC.variable} ${inter.variable}`}>
      <body className="pb-[calc(4rem+env(safe-area-inset-bottom))] text-text-primary min-h-screen antialiased font-body">
        {children}
        <Suspense fallback={null}>
          <BottomNav />
        </Suspense>
        <Suspense fallback={null}>
          <Analytics />
        </Suspense>
      </body>
    </html>
  );
}
