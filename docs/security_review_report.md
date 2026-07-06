# ITTF 网站安全与性能审查报告

生成时间：2026-07-06
审查范围：阿里云服务器 `xiaodoubao.site`（2 vCPU / 1.8 GB 内存 / 40G 磁盘，已用 82%），
nginx (`/etc/nginx/conf.d/data.xiaodoubao.site.conf`)，Docker 部署的 Next.js 15.2.8 Web 应用，
`data/db/ittf.db`（288 MB，WAL）。

## 执行摘要

应用层做得比预期好：反代已上 HTTPS（Certbot）、安全响应头齐全（CSP / X-Frame-Options / nosniff）、
密码用 scrypt + timingSafeEqual、认证接口有 Origin 校验和限流、SQL 全部走 better-sqlite3 参数化查询。
**主要风险不在应用代码本身，而在于服务器主机暴露面、边缘防护缺失，以及数据 API 完全开放可爬。**

按优先级需要处理的问题：

- **H1** 主机 `rpcbind`(111) 与 `8080` 监听在 `0.0.0.0`，暴露在公网攻击面 —— 需确认阿里云安全组是否放行。
- **H2** nginx 边缘无任何限流（`limit_req`/`limit_conn`），弱服务器对 CC/洪水攻击零缓冲。
- **H3** 全部 `/api/v1/*` 数据接口无鉴权、无限流、ID 可枚举 —— 整站数据可被免费爬走（你最关心的点）。
- **H4** 应用层限流依赖 `TRUST_PROXY_HEADERS`，配置不当会导致「全站共用一个限流桶」的自我 DoS，或被伪造 `X-Forwarded-For` 绕过。
- **M1** 无 fail2ban、SSH 登录策略未知，缺乏暴力破解防护。
- **M2** 备份目录 4.2 GB 堆积在仅剩 7 GB 的磁盘上，有写满风险。
- 其余中低危见下文。

---

## 高危 (High)

### H1 — 主机暴露面：rpcbind(111) 与 8080 监听全网卡

**证据**（`ss -tlnp`）：
```
LISTEN 0.0.0.0:80      nginx
LISTEN 0.0.0.0:443     nginx
LISTEN 0.0.0.0:8080    (另一个 nginx 静态站「小豆包的世界」)
LISTEN 0.0.0.0:22      sshd
LISTEN 0.0.0.0:111     rpcbind
LISTEN 127.0.0.1:3000  web_fate 容器
LISTEN 127.0.0.1:3001  ittf-web 容器
LISTEN 127.0.0.1:6379  redis (仅本地，OK)
```

**影响**：
- `rpcbind`(111) 是经典的 DDoS 反射放大源和历史漏洞集中地，服务器上没有跑 NFS 就完全不该开放公网。
- `8080` 把第二个站点直接裸暴露，绕过了 443 的 TLS 与安全头。

**修复**：
1. 确认阿里云 **安全组** 只放行 22 / 80 / 443，其余端口一律 `deny`（这是最省事、对弱机零开销的第一道防线）。
2. 关闭不需要的 rpcbind：
   ```bash
   sudo systemctl disable --now rpcbind.socket rpcbind.service
   ```
3. 8080 站点若需公网访问，应改为 127.0.0.1 监听 + 走 443 反代；若仅内部用，绑回 `127.0.0.1`。
4. 主机防火墙兜底（即使有安全组也建议加）：
   ```bash
   sudo firewall-cmd --permanent --add-service=http --add-service=https --add-service=ssh
   sudo firewall-cmd --permanent --remove-service=rpc-bind 2>/dev/null
   sudo firewall-cmd --reload
   ```

### H2 — nginx 边缘无限流，弱服务器无洪水缓冲

**证据**：`data.xiaodoubao.site.conf` 与 `nginx.conf` 中没有任何 `limit_req_zone` / `limit_conn_zone`。
应用层限流是「进程内内存计数」（`lib/server/ratelimit.ts`），且**只挂在认证接口上**，数据接口和整站入口都没有边缘保护。2 vCPU / 1.8 GB 的机器，几十并发的 CC 就能把 Next.js SSR 打满。

**修复**：在 `nginx.conf` 的 `http {}` 里定义限流区，在站点 `location` 里应用。见文末「附：nginx 加固片段」。核心是给 `/api/` 和认证接口更严的桶，静态资源放宽。

### H3 — 数据 API 完全开放、ID 可枚举，可被整站爬取

**证据**：`app/api/v1/{players,rankings,events,matches,compare,...}` 全部是公开 GET，无鉴权无限流；
`events/[eventId]`、`matches/[matchId]` 用连续数字 ID（`event_id=2860/3242` 等），可直接遍历。
且没有 `robots.txt`（`/robots.txt` 返回 404）。这意味着：整个爬了几个月的比赛/选手/排名数据库，别人可以用一个脚本几分钟拉全。

**这是你「防数据爬取」诉求的核心。现实地讲，公开展示的数据无法做到 100% 防爬**，但可以显著抬高成本：

1. **边缘限流按 IP + UA**（配合 H2），对 `/api/v1/` 设较低速率，正常用户翻页够用、批量抓取会被拖慢。
2. **加 `robots.txt`**（`app/robots.ts`），声明禁止爬取 `/api/`，至少挡住守规矩的爬虫，也是法律层面的「明确禁止」证据。
3. **给数据接口加缓存头 + nginx 缓存**（多数接口已是公开数据，缓存还能减轻弱机压力，一举两得）。
4. **考虑上 Cloudflare（免费版）**：DNS 套 CF 后自带 Bot 管理、CC 防护、缓存、隐藏源站 IP。对这台弱机是性价比最高的一招。若上 CF，记得把 `TRUST_PROXY_HEADERS=true`、`TRUSTED_PROXY_IP_HEADER=cf-connecting-ip`（应用已支持），并在安全组只放行 CF 回源 IP 段。
5. 长期可选：对最贵/最完整的聚合接口（如 `compare` 全量对战数据）要求登录后访问。

### H4 — 【已确认在线漏洞】限流可被伪造头绕过

**证据**：
- 服务器 `.env`：`TRUST_PROXY_HEADERS=true`，`TRUSTED_PROXY_IP_HEADER=cf-connecting-ip`。
- 但实测 `curl -sI https://data.xiaodoubao.site/` 返回 `Server: nginx/1.20.1`、**无 `cf-ray`**，
  DNS 直接解析到源站 `101.200.96.111` —— **网站当前并未真正走 Cloudflare**。
- `getClientIp()`（`lib/server/ratelimit.ts`）在信任开启时直接取 `cf-connecting-ip` 头的值作为客户端 IP。

**影响（现在就可利用）**：由于没有 CF 在前面剥离/覆盖该头，任何人都能自带一个伪造的
`cf-connecting-ip: <随机IP>` 直连源站。每换一个值就是一个全新的限流桶，于是登录/注册/发验证码的
限流形同虚设 —— 可无限撞库、可对任意邮箱轰炸验证码。

**修复（二选一）**：
- **方案 A（推荐，若近期不上 CF）**：把 `.env` 改成 `TRUSTED_PROXY_IP_HEADER=x-real-ip`。
  nginx 反代用 `proxy_set_header X-Real-IP $remote_addr;` 注入的是不可被客户端伪造的真实连接 IP，
  应用信任它才安全。同时 nginx 不要透传客户端 XFF（本次已在模板中改为 `X-Forwarded-For $remote_addr;`）。
- **方案 B（若上 Cloudflare）**：保持 `cf-connecting-ip`，但**必须**在阿里云安全组只放行 CF 回源 IP 段，
  否则有人直连源站照样能伪造该头。CF 回源前 nginx 还要用 realip 模块还原真实 IP（见 H2/附录）。

---

## 中危 (Medium)

### M1 — 无暴力破解防护 / SSH 策略未知
`fail2ban` 未运行（`inactive`）。建议：
```bash
sudo dnf install -y fail2ban
sudo systemctl enable --now fail2ban
```
最少启用 `sshd` jail；有余力再加 nginx `limit_req` 触发的 jail。同时确认 `/etc/ssh/sshd_config` 里
`PasswordAuthentication no`、`PermitRootLogin no`（我当前无 sudo 无法读取，请自查）。

### M2 — 备份堆积占满磁盘风险
`data/db/backups/` 已 **4.2 GB**，根分区 **已用 82%（仅剩 7 GB）**。cron 备份只保留 3 份，但各类
`ittf-before-*` 手动备份从 6 月累积了十几份，每份约 285 MB。磁盘写满会同时打挂 Web、SQLite 写入和抓取任务。
**修复**：清理旧的 `before-*` 备份、把备份轮转策略统一（如总量上限 / 只保留最近 N 份 / 定期下载到异地对象存储后删除本地）。

### M3 — SQLite 同步查询阻塞事件循环
better-sqlite3 是同步 API，288 MB 库上的重查询（如全量 `compare`、选手对手聚合）会**阻塞 Node 单事件循环**，
在 2 vCPU 上一个慢查询就能让并发请求排队。**修复**：给热点查询确认索引、对 `compare` 等昂贵接口加缓存头和 nginx 微缓存、必要时限并发。这与 H3 的缓存措施可合并实施。

### M4 — CSP 的 `script-src` 使用 `'unsafe-inline'`
`next.config.ts` 的 CSP 生产环境仍含 `'unsafe-inline'`（Next.js App Router 水合内联脚本导致，常见但会削弱 XSS 防护）。
当前应用没有富文本/用户 HTML 渲染，XSS 面很小，属**可接受的低优先级**。若将来引入用户内容，应改用 nonce 方案。

### M5 — nginx 安全日志规则形同虚设
`nginx.conf` 里 `map $request_body $is_malicious` 想记录恶意 body，但：
- `$request_body` 仅在 body 被 proxy 缓冲时才有值，且这套规则只「记录」不「拦截」。
- 规则针对 Node 原型链污染关键字，覆盖面很窄。
建议要么删掉降噪，要么升级为真正的拦截（`if ($is_malicious) { return 403; }`），并配合 H2 的限流。

---

## 低危 / 加固建议 (Low)

- **L1 `X-Powered-By: Next.js` 泄露技术栈**：`poweredByHeader: false` 关掉，少给指纹。
- **L2 nginx 未设 `server_tokens off`**：响应/错误页泄露 nginx 1.20.1 版本号。建议 `http {}` 加 `server_tokens off;`。
- **L3 `data.xiaodoubao.site.conf` 里 SSL 只启用了默认 protocols**：确认 `options-ssl-nginx.conf` 已禁用 TLS1.0/1.1（Certbot 默认较新，通常 OK，值得核对）。
- **L4 nginx 未启用 HTTP/2**：`listen 443 ssl;` 可加 `http2 on;`（1.25.1+ 语法）或旧写法，提升弱机下多资源加载性能。
- **L5 静态/头像资源反代经过 Node**：`/_next/static/`、`/images/avatar-*` 目前都 `proxy_pass` 回容器。可考虑 nginx 直接 `alias` 到宿主卷或加 nginx `proxy_cache`，把静态流量从 Node 卸载，对弱机帮助明显。
- **L6 开发用 `Upgrade/Connection "upgrade"` 头常驻生产**：生产 Next.js 不需要 HMR WebSocket，可移除，避免连接被长期挂起（配合弱机连接数控制）。

---

## 附：建议的 nginx 加固片段

`http {}` 块内（全局，放在 `include conf.d/*.conf;` **之前**）：
```nginx
server_tokens off;

# 限流区：按真实客户端 IP
limit_req_zone  $binary_remote_addr zone=api_limit:10m   rate=20r/s;
limit_req_zone  $binary_remote_addr zone=auth_limit:10m  rate=5r/m;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
```

`data.xiaodoubao.site.conf` 的 server 块内：
```nginx
# 全站每 IP 并发上限
limit_conn conn_limit 20;

location / {
    limit_req zone=api_limit burst=40 nodelay;   # 正常浏览够用，批量抓取会被拖慢
    proxy_pass http://127.0.0.1:3001;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $remote_addr;   # 不透传客户端伪造的 XFF
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
    client_max_body_size 2m;
}

# 认证接口更严
location /api/v1/auth/ {
    limit_req zone=auth_limit burst=5 nodelay;
    proxy_pass http://127.0.0.1:3001;
    proxy_set_header Host       $host;
    proxy_set_header X-Real-IP  $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`robots.txt`（新建 `web/app/robots.ts`）：
```ts
import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: '*', allow: '/', disallow: ['/api/'] }],
    sitemap: 'https://data.xiaodoubao.site/sitemap.xml',
  };
}
```
