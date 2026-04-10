import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ITTF Rankings · 女子单打',
  description: '展示 ITTF 女子单打排名、球员赛事与统计结果的轻量级站点。',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
