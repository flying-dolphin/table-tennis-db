import type { Metadata } from 'next';
import './globals.css';
import BottomNav from '@/components/BottomNav';

export const metadata: Metadata = {
  title: 'ITTF Rankings · 女子单打',
  description: '展示 ITTF 女子单打排名、球员赛事与统计结果的轻量级站点。',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="pb-24 text-text-primary min-h-screen antialiased font-body">
        {children}
        <BottomNav />
      </body>
    </html>
  );
}
