import type { MetadataRoute } from 'next';

// 声明爬虫策略：允许抓取公开页面，但禁止批量抓取 JSON 数据接口 (/api/)。
// robots.txt 只对守规矩的爬虫有效，真正的限流由 nginx 边缘 + 应用层承担。
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/monitoring'],
      },
    ],
  };
}
