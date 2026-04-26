# Cloudflare Deploy Checklist

Last updated: 2026-04-26

## Goal

Put the site behind Cloudflare as the primary public edge, then ensure the origin only accepts Cloudflare-validated traffic.

## SSL/TLS

1. Set SSL/TLS mode to `Full (strict)`.
2. Install a valid certificate on the origin.
3. If your plan supports it and you want stronger origin assurance, enable Authenticated Origin Pulls.

References:
- `https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/`
- `https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/set-up/zone-level/`

## Origin Protection

1. Do not expose the origin directly on the public Internet if you can avoid it.
2. Prefer firewall rules that only allow Cloudflare IP ranges to reach the app.
3. If you keep direct origin access for maintenance, restrict it to your admin IPs only.
4. In app config, set:

```env
APP_ORIGIN=https://your-domain.example
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IP_HEADER=cf-connecting-ip
SESSION_COOKIE_SECURE=true
```

## WAF

1. Turn on Cloudflare Managed Rules.
2. Review Security Events after enablement for false positives.
3. If your API/mobile traffic is sensitive to bot challenges, validate behavior before enabling broad bot protections.

## Bot Protection

1. Free plan baseline: enable Bot Fight Mode.
2. If you need endpoint-specific bypass/skip behavior, Bot Fight Mode is too coarse; use a more configurable bot product instead.

Reference:
- `https://developers.cloudflare.com/bots/get-started/free/`

## Rate Limiting Rules

Start with these route-focused rules:

1. `/api/v1/auth/login`
   - Match: `http.request.uri.path eq "/api/v1/auth/login"`
   - Count key: client IP
   - Suggested threshold: `10 requests / 15 minutes`
   - Action: Managed Challenge or Block

2. `/api/v1/auth/register`
   - Match: `http.request.uri.path eq "/api/v1/auth/register"`
   - Suggested threshold: `5 requests / 15 minutes`
   - Action: Managed Challenge or Block

3. `/api/v1/auth/send-code`
   - Match: `http.request.uri.path eq "/api/v1/auth/send-code"`
   - Suggested threshold: `5 requests / 1 minute`
   - Action: Managed Challenge or Block

4. `/api/v1/auth/logout`
   - Match: `http.request.uri.path eq "/api/v1/auth/logout"`
   - Suggested threshold: `30 requests / 5 minutes`
   - Action: Managed Challenge

Reference:
- `https://developers.cloudflare.com/waf/rate-limiting-rules/`
- `https://developers.cloudflare.com/waf/rate-limiting-rules/find-rate-limit/`

## Recommended Order

1. Proxy DNS through Cloudflare.
2. Switch SSL/TLS to `Full (strict)`.
3. Enable Managed Rules.
4. Enable route-specific rate limiting rules.
5. Enable bot protection.
6. Lock down origin ingress.
7. Verify production response headers and auth flows from the browser.

## Post-Deploy Verification

1. `Set-Cookie` includes `Secure`, `HttpOnly`, and `SameSite=Lax`.
2. Auth `POST` routes reject cross-origin requests.
3. Security headers are present:
   - `Content-Security-Policy`
   - `X-Content-Type-Options`
   - `Referrer-Policy`
   - `X-Frame-Options`
   - `Permissions-Policy`
4. Requests to the origin IP directly are blocked or otherwise unusable.
5. Cloudflare Security Events show rate-limited and challenged auth abuse traffic when tested.
