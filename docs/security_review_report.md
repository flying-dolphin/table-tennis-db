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

## 处理进度总览（2026-07-06）

| 步骤 | 内容 | 状态 |
|---|---|---|
| 1 | 【H4】`.env` 改 `TRUSTED_PROXY_IP_HEADER=x-real-ip`，堵限流绕过 | ✅ 已完成 |
| 2a | 【H1】阿里云安全组只放行 22/80/443 | ✅ 已完成 |
| 2b | 【H1】关闭 rpcbind(111) | ✅ 已完成 |
| 2c | 【H1】8080 Flask 站绑回 127.0.0.1（公网层已被 2a 挡住，此项为纵深加固） | ✅ 已完成 |
| 2d | 【H1】firewalld 兜底 | ➖ 不适用（firewalld 未运行，以阿里云安全组为准） |
| 3 | 【H2】nginx 边缘限流 `limit_req`/`limit_conn` + `server_tokens off` | ✅ 已完成 |
| 4a | 【H3】部署防爬代码（robots.ts / 去指纹 X-Powered-By） | ✅ 已完成 |
| 4b | 【H3】（可选）套 Cloudflare 免费版：CC 防护 / Bot 管理 / 隐藏源站 | ⬜ 待处理 |
| 5 | 【M1】fail2ban + 核对 sshd 策略 | ⬜ 待处理 |
| 6 | 【M2】清理备份、防磁盘写满 | ⬜ 待处理 |
| L | 低危加固（server_tokens/http2/静态卸载等） | ⬜ 待处理 |

> 已完成 1、2a/2b/2c、3、4a：最紧急的在线限流绕过漏洞、主机公网暴露面、nginx 边缘限流、
> 防爬代码均已上线。剩余为可选的 Cloudflare（4b）、fail2ban（5）、备份清理（6）与低危加固（L）。

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
1. ✅ 阿里云 **安全组** 已只放行 22 / 80 / 443，其余端口一律 `deny`（对弱机零开销的第一道防线）。
2. ✅ 已关闭 rpcbind：`sudo systemctl disable --now rpcbind.socket rpcbind.service`。
3. ✅ **8080 站点**：经排查是一个 **Flask 应用**（`Server: Werkzeug/3.0.4 Python/3.12.5`，
   `/root/.conda/envs/web/bin/python app.py`，以 **root** 运行），即 `xiaodoubao.site` /
   `xiaodoubao.club` 背后的站，nginx 已在 443 反代到 `localhost:8080`。
   已绑回 `127.0.0.1`（2a 安全组也已封 8080，双重保险）。
4. ➖ 主机 firewalld **未运行**，以阿里云安全组作为唯一防火墙即可，无需再起 firewalld
   （若日后要本机兜底可再启用，但对当前单机无必要）。

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

`robots.txt`（已落地 `web/app/robots.ts`）：
```ts
import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: '*', allow: '/', disallow: ['/api/', '/monitoring'] }],
  };
}
```

---

## 修复操作步骤（含进度标记）

> 图例：✅ 已完成　⬜ 待处理　➖ 不适用

### 已落地的代码改动（随下次部署生效）

| 文件 | 改动 |
|---|---|
| `web/app/robots.ts`（新增） | 声明禁止爬 `/api/`、`/monitoring` |
| `web/next.config.ts` | `poweredByHeader: false`，去掉 `X-Powered-By` 指纹 |
| `deploy/web/nginx.conf.example` | 加入 `limit_req`/`limit_conn`、`server_tokens off` 说明、真实 IP 处理、去掉伪造 XFF 透传 |

这三个改动要随镜像重新构建推送后才生效（见步骤 4）。

### ✅ 步骤 1 — 堵住限流绕过漏洞（H4）

已在线上 `.env` 将 `TRUSTED_PROXY_IP_HEADER` 改为 `x-real-ip`（`TRUST_PROXY_HEADERS=true` 不变），
并 `docker compose ... up -d` 生效。配合 nginx `proxy_set_header X-Real-IP $remote_addr;`（已有），
应用信任的是不可伪造的真实连接 IP。

### 步骤 2 — 收缩主机暴露面（H1）

- ✅ **2a 阿里云安全组**：入方向只保留 22（建议限来源 IP）、80、443；已删除 111/8080/3000/3001 等。
- ✅ **2b 关闭 rpcbind**：`sudo systemctl disable --now rpcbind.socket rpcbind.service`。
- ✅ **2c 8080 Flask 站绑回 127.0.0.1**（纵深加固，公网层已由 2a 关闭）：已把 `app.run` 的
  `host` 改为 `127.0.0.1` 并重启；`ss -tlnp | grep 8080` 现为 `127.0.0.1:8080`，站点访问正常。操作参考：
  ```bash
  # 1) 定位 app.py 的工作目录与文件（进程以 root 运行，需 sudo）
  sudo ls -l /proc/174357/cwd          # PID 见 `ps aux | grep app.py`，指向 app.py 所在目录
  # 2) 编辑 app.py，把监听地址从 0.0.0.0 改成 127.0.0.1：
  #      app.run(host='127.0.0.1', port=8080)   # 原来多半是 host='0.0.0.0'
  #    nginx 反代用的是 http://localhost:8080，改后照常工作。
  # 3) 重启该服务（取决于它怎么启动的：systemd / pm2 / screen / nohup）
  #      如是 systemd： sudo systemctl restart <服务名>
  #      如是裸进程： sudo kill 174357 后按原方式重新拉起
  # 4) 验证：ss -tlnp | grep 8080 应显示 127.0.0.1:8080；curl https://xiaodoubao.site 仍正常
  ```
  > 附注（另一层隐患，非本次范围）：该 Flask 站是 **Werkzeug 开发服务器**且**以 root 运行**。
  > 长期建议改用 gunicorn/uwsgi 生产服务器 + 非 root 用户运行，降低单点被攻破后的影响面。
- ➖ **2d firewalld 兜底**：firewalld 未运行，以阿里云安全组为唯一防火墙即可，无需启用。

### ✅ 步骤 3 — nginx 边缘限流（H2）

**3a.** 在 `/etc/nginx/nginx.conf` 的 `http {` 块**顶部**（务必先于 `include /etc/nginx/conf.d/*.conf;`）加入：
```nginx
server_tokens off;
limit_req_zone  $binary_remote_addr zone=api_limit:10m  rate=20r/s;
limit_req_zone  $binary_remote_addr zone=auth_limit:10m rate=5r/m;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
```
> ⚠️ 踩坑记录：这三行 `*_zone` **必须**定义在 `http {}` 里。若只改了站点 `.conf` 而漏了这步，
> `nginx -t` 会报 `[emerg] zero size shared memory zone "conn_limit"`（引用了未定义的区）。

**3b.** 站点 `/etc/nginx/conf.d/data.xiaodoubao.site.conf` 已更新为成品版（与 `deploy/web/nginx.conf.example`
一致）：`location /` 加 `limit_req zone=api_limit burst=50 nodelay;`；新增 `location /api/v1/auth/`
（`burst=5`）；`/images/`、`/_next/static/`、`/static/` **豁免限流**（避免一个页面几十张头像/chunk 误伤 429）；
`X-Forwarded-For` 改为 `$remote_addr;`；`listen 443 ssl http2;`（nginx 1.20.1 用 listen 上的 `http2` 参数，
不能用 `http2 on;`）；`proxy_read_timeout` 收到 60s。

**3c.** 校验并热加载：`sudo nginx -t && sudo systemctl reload nginx`。

**3d. 压测验证限流是否生效**：

限流按**速率**触发，串行 `for` 循环 curl 太慢（每次请求走完才发下一个），50 次刚好落在 burst=50 桶内，
所以**会全是 200 —— 这不代表没生效**。必须**并发**打、且总数明显超过 burst：
```bash
# 300 个请求 / 50 并发，统计各状态码数量
seq 1 300 | xargs -P 50 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
  https://data.xiaodoubao.site/api/v1/rankings | sort | uniq -c
# 预期：约 50 个 200（填满 burst 桶）+ 其余 429
```
若并发压测仍全是 200，才是配置问题，按序排查：
```bash
sudo nginx -T 2>/dev/null | grep -E "limit_req_zone|limit_req "   # 确认 zone 定义与 location 引用都在
sudo tail -f /var/log/nginx/error.log                            # 并发压时应刷出 limiting requests, zone "api_limit"
```
验证 HTTP/2：`curl -sI --http2 https://data.xiaodoubao.site/ | grep -i "^HTTP"`。

### 步骤 4 — 部署防爬代码 + 可选 Cloudflare（H3）

**✅ 4a. 部署已改代码**（robots.ts / poweredByHeader）：已构建推送镜像并在服务器 pull + up -d，
`curl -s https://data.xiaodoubao.site/robots.txt` 已返回 `Disallow: /api/`、响应头不再有 `X-Powered-By`。
参考命令：
```bash
# 开发机
cd ~/projects/ittf && bash deploy/web/build-and-push.sh
# 服务器
docker compose -f ~/doubao_tt/deploy/web/docker-compose.yml --env-file ~/doubao_tt/deploy/web/.env pull web
docker compose -f ~/doubao_tt/deploy/web/docker-compose.yml --env-file ~/doubao_tt/deploy/web/.env up -d
curl -s https://data.xiaodoubao.site/robots.txt   # 应出现 Disallow: /api/
```
**⬜ 4b.（强烈建议）套 Cloudflare 免费版**：NS 指向 CF、`data` 记录开橙云；缓存 `/_next/static/`、`/static/`、头像；
回源改回 `TRUSTED_PROXY_IP_HEADER=cf-connecting-ip` + nginx realip 模块还原真实 IP + 安全组只放行 CF 回源 IP；
用 CF Rate Limiting / Bot Fight Mode 对 `/api/` 加规则。

### ⬜ 步骤 5 — 暴力破解防护（M1）

```bash
sudo dnf install -y fail2ban
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```
核对 `/etc/ssh/sshd_config`：`PasswordAuthentication no`、`PermitRootLogin no`
（改后 `sudo systemctl reload sshd`，务必先确认密钥登录可用，别把自己锁在外面）。

### ⬜ 步骤 6 — 清理备份、防磁盘写满（M2）

```bash
cd ~/doubao_tt/data/db/backups && ls -lt        # 先看
rm -f ittf-before-*20260617* ittf-before-*20260626* ittf-before-*20260627* ittf.db ittf.db-shm ittf.db-wal
df -h /                                          # 确认释放
```
长期：把备份定期 `ossutil cp` 到阿里云 OSS 后删本地，或给 `before-*` 也加保留上限。

### ⬜ 低危加固清单（L）

- L1/L2：`poweredByHeader:false`（已改代码）+ `server_tokens off`（步骤 3a）。
- L3：`grep TLSv1 /etc/letsencrypt/options-ssl-nginx.conf` 确认无 `TLSv1 TLSv1.1`。
- L4：nginx 443 开 `http2 on;`。
- L5：静态/头像用 nginx `alias` 宿主卷或 `proxy_cache`，把流量从 Node 卸载。
- L6：生产 `location /` 去掉 `Upgrade`/`Connection "upgrade"` 两行。
