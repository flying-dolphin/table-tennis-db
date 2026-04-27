import type { NextConfig } from 'next';
import { withSentryConfig } from '@sentry/nextjs';

function getOrigin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function buildCsp() {
  const isProduction = process.env.NODE_ENV === 'production';
  const umamiOrigin = getOrigin(process.env.NEXT_PUBLIC_UMAMI_URL);
  const sentryDsnOrigin = getOrigin(process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN);

  // Next.js App Router relies on inline scripts for hydration and flight data bootstrapping.
  const scriptSrc = ["'self'", "'unsafe-inline'"];
  if (!isProduction) scriptSrc.push("'unsafe-eval'");
  if (umamiOrigin) scriptSrc.push(umamiOrigin);
  if (process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID) scriptSrc.push('https://www.clarity.ms', 'https://*.clarity.ms');

  const connectSrc = ["'self'"];
  if (umamiOrigin) connectSrc.push(umamiOrigin);
  if (sentryDsnOrigin) connectSrc.push(sentryDsnOrigin);
  if (process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID) connectSrc.push('https://*.clarity.ms', 'https://c.bing.com');

  const imgSrc = ["'self'", 'data:', 'blob:', 'https://api.dicebear.com'];
  if (sentryDsnOrigin) imgSrc.push(sentryDsnOrigin);
  if (process.env.NEXT_PUBLIC_CLARITY_PROJECT_ID) {
    imgSrc.push('https://c.clarity.ms', 'https://*.clarity.ms', 'https://c.bing.com');
  }

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSrc.join(' ')}`,
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data:",
    `img-src ${imgSrc.join(' ')}`,
    `connect-src ${connectSrc.join(' ')}`,
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];

  if (isProduction) {
    directives.push('upgrade-insecure-requests');
  }

  return directives.join('; ');
}

const nextConfig: NextConfig = {
  // standalone 输出：Next.js 通过 output file tracing 只把运行时真正用到的
  // 依赖打进 .next/standalone/，避免把整个 node_modules（含 dev 依赖）塞进镜像
  output: 'standalone',
  experimental: {
    typedRoutes: true,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.dicebear.com',
      },
    ],
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: buildCsp(),
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

const sentryEnabled = Boolean(
  process.env.SENTRY_AUTH_TOKEN && process.env.SENTRY_ORG && process.env.SENTRY_PROJECT,
);

export default sentryEnabled
  ? withSentryConfig(nextConfig, {
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      silent: !process.env.CI,
      widenClientFileUpload: true,
      tunnelRoute: '/monitoring',
      webpack: {
        treeshake: {
          removeDebugLogging: true,
        },
        automaticVercelMonitors: false,
      },
    })
  : nextConfig;
