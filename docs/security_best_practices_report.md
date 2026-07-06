# Security Best Practices Report

Date: 2026-04-26
Scope: `web/` Next.js application and auth-related backend routes

## Executive Summary

The site is not yet ready for direct public deployment without additional hardening. The most important issues are an outdated `Next.js` version affected by an official security advisory, missing `Secure` flags on session cookies, weak CSRF posture on cookie-authenticated state-changing routes, and rate limiting that will not hold under multi-instance or serverless deployment. There is no strong evidence of SQL injection or obvious React HTML injection sinks in the current code, but the production security baseline is still incomplete.

## Critical / High

### SBP-001
- Severity: High
- Rule ID: NEXT-SUPPLY-001
- Location: [web/package.json](/D:/dev/project/ittf/web/package.json:18)
- Evidence:

```json
"next": "15.2.4"
```

- Impact: The deployed application may be exposed to a known framework-level vulnerability if published with an affected Next.js release.
- Fix: Upgrade `next` to an official patched version in the same line or newer supported line. Based on the later official December 11, 2025 security update, `15.2.8` is the fixed `15.2.x` release.
- Mitigation: Keep production behind a reverse proxy/WAF while upgrading, but do not treat that as a substitute for patching.
- False positive notes: Verify the final installed version in `package-lock.json` and runtime build output after the upgrade.

Notes:
- Official advisory: `https://nextjs.org/blog/CVE-2025-66478`
- Later security update: `https://nextjs.org/blog/security-update-2025-12-11`
- Official support policy: `https://nextjs.org/support-policy`

### SBP-002
- Severity: High
- Rule ID: NEXT-SESS-001
- Location:
  - [web/app/api/v1/auth/login/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/login/route.ts:44)
  - [web/app/api/v1/auth/register/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/register/route.ts:74)
  - [web/app/api/v1/auth/logout/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/logout/route.ts:10)
- Evidence:

```ts
response.cookies.set(SESSION_COOKIE, token, {
  httpOnly: true,
  sameSite: 'lax',
  maxAge,
  path: '/',
});
```

- Impact: If production traffic is ever exposed over plain HTTP or through a misconfigured proxy path, the session cookie may be transmitted without transport protection.
- Fix: Set `secure: true` in production for all session cookie writes and clears. Gate it on environment if local HTTP development must continue to work.
- Mitigation: Enforce HTTPS end-to-end and ensure the origin is not directly reachable over plain HTTP.
- False positive notes: If a platform or framework layer rewrites cookies before egress, verify the actual `Set-Cookie` header at runtime.

### SBP-003
- Severity: High
- Rule ID: NEXT-CSRF-001
- Location: [web/app/api/v1/auth/logout/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/logout/route.ts:5)
- Evidence:

```ts
export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) deleteSession(token);
```

- Impact: A third-party site can trigger a logout request from the victim browser because the route relies on cookies and does not perform explicit origin or token validation.
- Fix: Add strict `Origin` validation for cookie-authenticated state-changing routes. If additional sensitive actions are added later, introduce a reusable CSRF defense layer.
- Mitigation: `SameSite=Lax` reduces some cross-site request scenarios, but it is not a complete CSRF defense.
- False positive notes: This finding is directly applicable even if the immediate effect is “only logout”, because it confirms the state-changing cookie route pattern is currently unprotected.

## Medium

### SBP-004
- Severity: Medium
- Rule ID: NEXT-DOS-001
- Location:
  - [web/lib/server/ratelimit.ts](/D:/dev/project/ittf/web/lib/server/ratelimit.ts:6)
  - [web/app/api/v1/auth/login/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/login/route.ts:8)
  - [web/app/api/v1/auth/register/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/register/route.ts:11)
  - [web/app/api/v1/auth/send-code/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/send-code/route.ts:11)
- Evidence:

```ts
const store = new Map<string, Bucket>();
```

```ts
const ip = request.headers.get('x-forwarded-for') ?? 'local';
```

- Impact: Rate limits reset on process restart, do not coordinate across instances, and can become ineffective in serverless or horizontally scaled production deployments. If the origin is reachable directly, trusting `x-forwarded-for` also enables spoofing.
- Fix: Move rate limiting to a shared store or edge layer. For deployment, put primary abuse controls in Cloudflare rate limiting and ensure the origin only trusts proxy headers from Cloudflare.
- Mitigation: Keep the in-process limiter as a weak secondary fallback until edge protections are in place.
- False positive notes: If the final production platform is single-instance only, the current limiter still works partially, but it remains weak for public auth endpoints.

### SBP-005
- Severity: Medium
- Rule ID: NEXT-HEADERS-001
- Location:
  - [web/next.config.ts](/D:/dev/project/ittf/web/next.config.ts:4)
  - [web/app/layout.tsx](/D:/dev/project/ittf/web/app/layout.tsx:29)
  - [web/components/Analytics.tsx](/D:/dev/project/ittf/web/components/Analytics.tsx:91)
- Evidence:

`web/next.config.ts` has no `headers()` security header configuration, while the app loads third-party analytics and an inline script:

```tsx
<Script
  src={`${UMAMI_URL}/script.js`}
  data-website-id={UMAMI_WEBSITE_ID}
  data-auto-track="false"
  strategy="afterInteractive"
/>
```

```tsx
<Script id="ms-clarity" strategy="afterInteractive">
```

- Impact: The site currently lacks a visible CSP and related baseline headers, so browser-side defense-in-depth against XSS, clickjacking, and MIME confusion is weaker than production baseline expectations.
- Fix: Add production security headers, especially `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, and `frame-ancestors` or `X-Frame-Options`. Account for required analytics domains and inline script strategy.
- Mitigation: If headers are already enforced at CDN or reverse proxy, verify them at runtime and document that source of truth.
- False positive notes: This finding is based on repo-visible app config only. An external platform layer may already inject headers.

### SBP-006
- Severity: Medium
- Rule ID: NEXT-INPUT-001 / REACT-CSRF-001
- Location: [web/app/auth/page.tsx](/D:/dev/project/ittf/web/app/auth/page.tsx:101)
- Evidence:

```ts
const res = await fetch("/api/v1/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ email: loginEmail, password: loginPassword }),
});
```

- Impact: The frontend explicitly uses cookie-based authenticated requests, which confirms that future state-changing routes will remain CSRF-relevant unless the backend standardizes origin/token checks.
- Fix: Standardize a backend-side CSRF/origin validation helper for cookie-authenticated `POST` routes and apply it consistently.
- Mitigation: Restricting routes to same-origin usage and keeping `SameSite=Lax` helps but is not sufficient as a policy boundary.
- False positive notes: This is not a separate exploit by itself; it reinforces the backend CSRF finding.

## Low / Defense-in-Depth

### SBP-007
- Severity: Low
- Rule ID: NEXT-LOG-001
- Location: [web/app/api/v1/auth/send-code/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/send-code/route.ts:45)
- Evidence:

```ts
console.error('[send-code] mail error:', err);
```

- Impact: Transport or provider errors may leak more operational detail than needed into logs, depending on the mailer error object.
- Fix: Log a narrower structured error payload and avoid dumping full provider error objects when not needed.
- Mitigation: If server logs are tightly controlled, this is mainly an operational hygiene issue.
- False positive notes: I did not observe direct credential logging in app code.

### SBP-008
- Severity: Low
- Rule ID: NEXT-DOS-001
- Location:
  - [web/app/api/v1/auth/send-code/route.ts](/D:/dev/project/ittf/web/app/api/v1/auth/send-code/route.ts:35)
  - [web/lib/server/auth.ts](/D:/dev/project/ittf/web/lib/server/auth.ts:95)
- Evidence:

```ts
if (existing) {
  return error(409, 4091, '该邮箱已被注册');
}
```

```ts
export function verifyEmailCode(email: string, code: string): boolean {
```

- Impact: The API allows registered-email enumeration and does not appear to separately throttle repeated verification attempts per email/code pair.
- Fix: Consider normalizing outward responses for the send-code flow and add attempt throttling for verification.
- Mitigation: Strong edge rate limiting will reduce abuse but will not eliminate enumeration behavior.
- False positive notes: This is lower severity than the session and framework issues because it does not directly expose authenticated access.

## Findings Not Confirmed

- I did not find clear SQL injection in the reviewed `web/` server query paths. Most database access uses prepared statements with bound parameters.
- I did not find `dangerouslySetInnerHTML` or other obvious React HTML injection sinks in the application code that was searched.
- I did not find evidence that `.env` is committed to git; `.gitignore` excludes `.env`, and `git ls-files` only showed `.env.example`.

## Deployment Recommendations

### Before Public Launch

1. Upgrade `Next.js` to a patched supported version.
2. Add `Secure` session cookies in production.
3. Add explicit CSRF/origin checks to cookie-authenticated state-changing routes.
4. Move abuse protection to edge and/or shared-store rate limiting.
5. Add production security headers and verify them in runtime responses.
6. Ensure the origin only accepts traffic from the chosen reverse proxy/CDN.

### Cloudflare Recommendation

Cloudflare is recommended as an external protection layer, especially if the site will be self-hosted or directly internet-facing. It should not replace code-level fixes, but it is worthwhile for:

1. Managed WAF rules.
2. Rate limiting rules on:
   - `/api/v1/auth/login`
   - `/api/v1/auth/register`
   - `/api/v1/auth/send-code`
   - `/api/v1/auth/logout`
3. Bot mitigation.
4. TLS termination and origin shielding.
5. Centralized header enforcement if you choose CDN-level control.

Useful references:
- `https://developers.cloudflare.com/waf/rate-limiting-rules/`
- `https://developers.cloudflare.com/bots/get-started/bot-fight-mode/`
- `https://developers.cloudflare.com/waf/feature-interoperability/`
