# ITTF 项目部署文档

本文档覆盖 ITTF 排名站点从零部署上线的完整流程：Web 应用、镜像仓库、远程数据抓取与同步、埋点与监控。

> 文件名沿用历史命名 `DEPLOY_ANALYTICS.md`，但内容是整个项目的部署说明。

---

## 一、整体架构

### 拓扑

```
                                     Internet
                                        │
                                        ▼
                                  Cloudflare Edge
                           (DNS Proxy / WAF / Rate Limit)
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
         ittf.your-domain.com                      analytics.your-domain.com
                               ┌────────────────────┐    ┌──────────────────────┐
                               │     服务器 A         │    │      服务器 B         │
                               │   主业务 + 数据      │    │    Umami 独立部署     │
                               │                    │    │                      │
   ┌──────────────────────┐   │  ┌──────────────┐  │    │  ┌────────────────┐  │
   │   本地抓取服务器       │   │  │  Next.js Web │  │    │  │     Umami      │  │
   │                      │   │  │ (docker:3000)│  │    │  │ (docker:3001)  │  │
   │  cron + sentry-cli   │   │  └──────┬───────┘  │    │  └────────┬───────┘  │
   │   ↓                  │   │         │ reads    │    │           │          │
   │  Python 抓取 + 导入   │   │  ┌──────▼───────┐  │    │  ┌────────▼───────┐  │
   │  → 本地 SQLite        │   │  │ SQLite 数据库 │  │    │  │ PostgreSQL 专用 │  │
   │  → .backup 快照       ├──►│  │ /opt/ittf/   │  │    │  └────────────────┘  │
   │  rsync 推送 ─────────►│   │  │  data/db/    │  │    │                      │
   │                      │   │  │  ittf.db     │  │    │  与服务器 A 完全隔离   │
   └──────────┬───────────┘   │  └──────────────┘  │    └──────────────────────┘
              │               └────────────────────┘                ▲
              │                                                     │ POST 事件
              ▼                                                     │
   ┌─────────────────────────┐               浏览器 ─────────────────┘
   │  阿里云 ACR 镜像仓库      │                   │
   │  crpi-...../doubao_web  │◄──────镜像 pull─── │
   └─────────────────────────┘                   │
              ▲                                  │
              │ docker push                      │
   ┌──────────┴──────────┐                       │
   │  开发机（Win/Mac）   │                       │
   │  build-and-push.sh  │              ┌────────┴────────┐
   └─────────────────────┘              │   SaaS 服务      │
                                        │ Sentry / Clarity │
                                        │   SMTP（163）    │
                                        └──────────────────┘
```

### 角色分工

| 组件 | 部署在 | 形态 | 作用 |
|------|--------|------|------|
| 阿里云 ACR | 阿里云 | SaaS（个人版免费） | 存放 Web 镜像 |
| Next.js Web | 服务器 A | Docker 容器（pull from ACR） | 对外 SSR + API |
| SQLite 数据库 | 服务器 A | 宿主文件 `/opt/ittf/data/db/ittf.db` | 网站读取的真实数据 |
| Cloudflare | 边缘 | SaaS | DNS 代理、WAF、Bot、防刷、TLS 入口 |
| Nginx + 源站证书 | 服务器 A | 宿主 | 仅供 Cloudflare 回源的反代 + HTTPS |
| Python 抓取 | **本地服务器**（家里/Mac mini/办公室机） | host venv + cron | 拉数据、导入本地 SQLite、rsync 到 A |
| Sentry Cron Monitor | SaaS | 无部署 | 监控本地 cron 是否按时跑、是否失败 |
| Umami | 服务器 B | Docker 容器 | 流量与事件分析 |
| Umami PostgreSQL | 服务器 B | Docker 容器（专用） | Umami 自己的库 |
| Microsoft Clarity | SaaS | 无部署 | 热力图、会话回放 |
| Sentry | SaaS | 无部署 | 错误监控 |
| SMTP | SaaS（163 等） | 无部署 | 邮箱验证码 |

### 关键设计取舍

- **Python 抓取放本地服务器**：playwright + chromium 镜像约 1GB，且抓取低频；放本地（家用/办公）随便挂，避免污染公网服务器。
- **数据流向单向**：本地 → A，A 永不写回。简单可靠，备份方便。
- **服务器 A 不需要 Python 环境**：A 上只有 docker 和 nginx。
- **镜像仓库用阿里云 ACR**：build 在开发机，服务器 A 只 pull，省服务器内存（不用 build），版本可回滚。
- **所有 SaaS 用免费版**：Sentry / Clarity / Sentry Crons 都有充足的免费额度。
- **环境变量分三类**（重要）：
  - **公开 [build-arg]**：`NEXT_PUBLIC_*`、`SENTRY_ORG`、`SENTRY_PROJECT`——会内联进客户端 bundle 或镜像 ENV，改后必须重新 build 镜像
  - **机密 [secret]**：`SENTRY_AUTH_TOKEN`——通过 BuildKit `--mount=type=secret` 在 build 时临时挂载，**绝不进任何镜像 layer 或 docker history**
  - **运行时 [runtime]**：`SMTP_PASS`、`SENTRY_DSN`、`ITTF_DATA_DIR`、`APP_ORIGIN` 等——只在 `up` 时通过宿主环境注入容器，不在镜像中
- **CSP 策略由 Next.js 自动生成**：`web/next.config.ts` 的 `buildCsp()` 会根据 `NEXT_PUBLIC_UMAMI_URL`、`NEXT_PUBLIC_CLARITY_PROJECT_ID`、`NEXT_PUBLIC_SENTRY_DSN` 或 `SENTRY_DSN` 自动拼接白名单。环境变量一变，最终下发的 CSP 也会变；排查前端资源被拦时要先核对生产环境变量。
- **生产环境默认假设站点前面有受信任代理**：当前安全配置已支持 Cloudflare 场景，包括 `APP_ORIGIN` 同源校验、`SESSION_COOKIE_SECURE`、以及 `cf-connecting-ip` 客户端 IP 识别。正式上线建议把 Cloudflare 放进主路径，而不是把源站直接暴露公网。

---

## 二、首次部署的步骤依赖

```
步骤             依赖
────────────    ─────────────────────────
1. DNS 解析      —
2. SaaS 注册     拿到所有 ID/Token (Sentry / Clarity / SMTP)
3. 服务器 B      部署 Umami → 拿到 Website ID
4. 阿里云 ACR    创建命名空间 → 拿到访问凭证
5. 开发机 build  把第 2、3 步的 ID 内联进镜像 → push 到 ACR
6. Cloudflare    代理 DNS → Full (strict) → WAF / Rate Limiting / Bot
7. 服务器 A      pull 镜像 → 起容器 + nginx
8. 本地服务器    部署抓取 + rsync + Sentry Cron
9. 验证清单      逐项打勾
```

务必按顺序：第 5 步 build 时需要第 2、3 步拿到的 ID，先后颠倒会要返工。

---

## 三、SaaS 服务注册

### 3.1 Sentry（错误监控 + Cron Monitor）

1. 注册 https://sentry.io → 选 Next.js platform → 创建项目，记下 **DSN**
2. **Settings → Auth Tokens → Create New Token**：勾选 `project:read`、`project:releases`、`project:write`、`org:read`，记下 token
3. 记下：`DSN`、`Org slug`、`Project slug`、`Auth Token`
4. **Crons**（菜单里）→ 后续创建 monitor 用，本步暂不需要

### 3.2 Microsoft Clarity（热力图 + 会话回放）
1. 用微软账号登录 https://clarity.microsoft.com
2. **New Project** → 站点名 + 未来对外域名（`ittf.your-domain.com`）
3. **Setup** 页面复制 **Project ID**

### 3.3 SMTP（邮箱验证码）
准备 `SMTP_HOST / PORT / USER / PASS / FROM`。授权码不是登录密码，到邮箱后台开通 SMTP 时单独生成。

### 3.4 阿里云 ACR（镜像仓库）

ACR 个人版：免费、私有、华北 2（北京）、不限存储、200GB/月公网拉取流量。

1. 控制台 → 容器镜像服务 ACR → 个人实例
2. 命名空间已是 `doubao_tt`
3. 仓库 `doubao_web` 已存在，公网地址：
   ```
   crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web
   ```
4. **访问凭证 → 设置固定密码**，记下：
   - Username：阿里云账号全名（带 `@xxx.aliyun.com` 后缀）
   - Password：你设置的固定密码

> 个人版不支持子账号，所以开发机和服务器 A 用的都是同一对凭证。

---

## 四、服务器 B：部署 Umami

完整步骤详见 [`deploy/umami/README.md`](../deploy/umami/README.md)：

```bash
scp -r deploy/umami user@serverB:/opt/
ssh user@serverB
cd /opt/umami
echo "UMAMI_DB_PASSWORD=$(openssl rand -hex 24)" > .env
echo "UMAMI_APP_SECRET=$(openssl rand -hex 32)" >> .env
chmod 600 .env
docker compose up -d

sudo cp nginx.conf.example /etc/nginx/conf.d/umami.conf
sudo sed -i 's/analytics.example.com/analytics.your-domain.com/g' /etc/nginx/conf.d/umami.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d analytics.your-domain.com
```

浏览器登录 `https://analytics.your-domain.com`（默认 admin/umami → **立即改密码**），Settings → Websites → Add → 拿到 **Website ID（UUID）**。

---

## 五、开发机：构建并推送镜像到 ACR

### 5.1 一次性准备

```bash
# 登录 ACR（输入 ACR 控制台设置的固定密码）
docker login crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
```

### 5.2 准备 build 时变量

在仓库根：
```bash
cp deploy/web/.env.example deploy/web/.env
chmod 600 deploy/web/.env
$EDITOR deploy/web/.env
```

把第三、四节拿到的全部 ID/DSN/Token 填进去，特别是：
- `NEXT_PUBLIC_UMAMI_URL` / `NEXT_PUBLIC_UMAMI_WEBSITE_ID`
- `NEXT_PUBLIC_CLARITY_PROJECT_ID`
- `NEXT_PUBLIC_SENTRY_DSN` / `SENTRY_ORG` / `SENTRY_PROJECT`
- `SENTRY_AUTH_TOKEN`（**机密**：不会进镜像 layer，但要正确填，否则 source map 上传失败）

> **机密保护**：`SENTRY_AUTH_TOKEN` 通过 BuildKit `--mount=type=secret` 传给 webpack 插件，
> 在 build 单步 RUN 内可读，build 结束销毁。`docker history`、`docker inspect` 都看不到它，
> 即使有人拿到镜像也无法反推 token。其它 `--build-arg` 列表里的变量都是公开标识符。

> **Windows 下提示**：build-and-push.sh 是 bash 脚本，请在 WSL / Git Bash 里跑；或者用第 5.4 节的手动命令在 PowerShell 里跑。

### 5.3 自动构建 + 推送（推荐）

```bash
# 用 git short sha 作 tag
./deploy/web/build-and-push.sh

# 或者用语义版本
./deploy/web/build-and-push.sh v1.0.0
```

脚本会：
1. 加载 `deploy/web/.env`
2. `docker build` 并打两个 tag：`<指定 tag>` 和 `latest`
3. `docker push` 两个 tag

### 5.4 手动命令（PowerShell / 不想用脚本时）

```bash
export DOCKER_BUILDKIT=1
TAG=$(git rev-parse --short HEAD)
IMAGE=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web

# 把 SENTRY_AUTH_TOKEN 放进当前 shell 环境（不要写到命令行参数里！）
export SENTRY_AUTH_TOKEN=<sentry-auth-token>

# 在仓库根目录跑
docker build \
    -f deploy/web/Dockerfile \
    -t $IMAGE:$TAG -t $IMAGE:latest \
    --build-arg NEXT_PUBLIC_UMAMI_URL=https://analytics.your-domain.com \
    --build-arg NEXT_PUBLIC_UMAMI_WEBSITE_ID=<umami-uuid> \
    --build-arg NEXT_PUBLIC_CLARITY_PROJECT_ID=<clarity-id> \
    --build-arg NEXT_PUBLIC_SENTRY_DSN=https://...@sentry.io/... \
    --build-arg NEXT_PUBLIC_SENTRY_ENV=production \
    --build-arg SENTRY_ORG=<org> \
    --build-arg SENTRY_PROJECT=<project> \
    --secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN \
    .
docker push $IMAGE:$TAG
docker push $IMAGE:latest

# 可选：build 完成后清掉 shell 里的 token，避免 history 留痕
unset SENTRY_AUTH_TOKEN
```

PowerShell 版本：
```powershell
$env:DOCKER_BUILDKIT=1
$env:SENTRY_AUTH_TOKEN = "<sentry-auth-token>"
$TAG = git rev-parse --short HEAD
$IMAGE = "crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web"

docker build `
    -f deploy/web/Dockerfile `
    -t "$IMAGE:$TAG" -t "$IMAGE:latest" `
    --build-arg NEXT_PUBLIC_UMAMI_URL=https://analytics.your-domain.com `
    --build-arg NEXT_PUBLIC_UMAMI_WEBSITE_ID=<umami-uuid> `
    --build-arg NEXT_PUBLIC_CLARITY_PROJECT_ID=<clarity-id> `
    --build-arg NEXT_PUBLIC_SENTRY_DSN=https://...@sentry.io/... `
    --build-arg NEXT_PUBLIC_SENTRY_ENV=production `
    --build-arg SENTRY_ORG=<org> `
    --build-arg SENTRY_PROJECT=<project> `
    --secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN `
    .
docker push "$IMAGE:$TAG"
docker push "$IMAGE:latest"
Remove-Item Env:SENTRY_AUTH_TOKEN
```

⚠️ **不要**用 `--build-arg SENTRY_AUTH_TOKEN=$TOKEN` 这种写法，它会被记录在 `docker history` 里。
统一通过 `--secret` 传，让 token 只在 BuildKit 的 tmpfs 挂载里存在那一瞬间。

---

## 六、服务器 A：起 Web 容器

### 6.1 一次性准备

```bash
# 创建项目目录与 deploy 用户（用于本地服务器 ssh 推送）
sudo mkdir -p /opt/ittf
sudo useradd -m -G docker deploy
sudo chown -R deploy:deploy /opt/ittf

# 装 nginx + certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# 切到 deploy 用户拉代码（仅 deploy/ 目录就够，源码不需要）
sudo -u deploy -i
cd /opt/ittf
git clone <repo-url> .            # 或者只 scp 部分目录
mkdir -p data/db data/rankings data/player_profiles data/player_avatars data/matches_complete
```

### 6.2 ACR 登录

```bash
# 在服务器 A 上同样登录 ACR（输入与开发机相同的固定密码）
docker login crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
```

### 6.3 配 .env

```bash
cd /opt/ittf
cp deploy/web/.env.example deploy/web/.env
chmod 600 deploy/web/.env
$EDITOR deploy/web/.env
```

服务器 A 的 `.env` 里只有**运行时变量**真正起作用，build args 已经被烘进镜像了。但仍建议把 build args 也填上，方便回头需要时一键 build。

生产环境至少确认这些运行时变量已经填好：

```env
ITTF_WEB_IMAGE=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web:vX.Y.Z
ITTF_DATA_DIR=/opt/ittf/data
APP_ORIGIN=https://ittf.your-domain.com
SESSION_COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IP_HEADER=cf-connecting-ip
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENV=production
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_SECURE=true
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=...
```

说明：

- `APP_ORIGIN`：认证类 `POST` 接口会校验 `Origin`，生产环境必须配置成最终对外域名。
- `SESSION_COOKIE_SECURE=true`：强制会话 Cookie 只经 HTTPS 发送。
- `TRUST_PROXY_HEADERS=true` + `TRUSTED_PROXY_IP_HEADER=cf-connecting-ip`：仅在前面接了 Cloudflare 这类受信任代理时开启，用于限流识别真实客户端 IP。
- `ITTF_WEB_IMAGE`：固定到明确 tag，避免 `latest` 漂移。

确认 `ITTF_WEB_IMAGE` 已指向你要部署的 tag：
```
ITTF_WEB_IMAGE=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web:vX.Y.Z
```

### 6.4 准备初始 SQLite 数据

把开发机现有的 `data/db/ittf.db` scp 上去：
```bash
# 在开发机
scp data/db/ittf.db deploy@serverA:/opt/ittf/data/db/
```

后续会被本地服务器的 cron 自动覆盖更新（见第八节）。

### 6.5 拉镜像 + 起容器

```bash
cd /opt/ittf
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env pull web
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env up -d
docker compose -f deploy/web/docker-compose.yml logs -f web
```

### 6.6 配 Nginx + TLS

```bash
sudo cp /opt/ittf/deploy/web/nginx.conf.example /etc/nginx/conf.d/ittf.conf
sudo sed -i 's/ittf.example.com/ittf.your-domain.com/g' /etc/nginx/conf.d/ittf.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ittf.your-domain.com
```

### 6.7 Cloudflare 接入与源站保护

推荐把 Cloudflare 作为正式公网入口，再让服务器 A 只接受 Cloudflare 回源。

1. 在 Cloudflare 中把 `ittf.your-domain.com` 切到代理模式。
2. `SSL/TLS` 设为 `Full (strict)`。
3. 打开 `Managed Rules`。
4. 给认证接口配置单独的 rate limiting：
   - `/api/v1/auth/login`：建议 `10 requests / 15 minutes`
   - `/api/v1/auth/register`：建议 `5 requests / 15 minutes`
   - `/api/v1/auth/send-code`：建议 `5 requests / 1 minute`
   - `/api/v1/auth/logout`：建议 `30 requests / 5 minutes`
5. 免费版至少启用 `Bot Fight Mode`；如果后续需要更细粒度跳过规则，再升级到更可控的 bot 防护方案。
6. 在源站防火墙或安全组上限制入站，只允许 Cloudflare IP 段访问 80/443；如果必须保留直连维护通道，只放你的管理 IP。
7. 如果套餐和运维条件允许，再考虑开启 `Authenticated Origin Pulls` 进一步收紧源站鉴权。

更完整的逐项核对见 [`docs/CLOUDFLARE_DEPLOY_CHECKLIST.md`](./CLOUDFLARE_DEPLOY_CHECKLIST.md)。

---

## 七、Web 应用日常更新（手动发版流程）

```
开发机改代码 → commit → ./deploy/web/build-and-push.sh
                                       │
                                       ▼
                          阿里云 ACR (新 tag 镜像)
                                       │
                                       ▼
SSH 服务器 A → 编辑 .env 改 ITTF_WEB_IMAGE → pull + up -d
```

具体命令：
```bash
# 1. 开发机
git pull && git status   # 确认是干净的
./deploy/web/build-and-push.sh           # 输出 ":xxxxxxx" tag
# 例如：Pushed crpi-...:a1b2c3d

# 2. 服务器 A
ssh deploy@serverA
cd /opt/ittf
sed -i 's|^ITTF_WEB_IMAGE=.*|ITTF_WEB_IMAGE=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com/doubao_tt/doubao_web:a1b2c3d|' deploy/web/.env
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env pull web
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env up -d
docker compose -f deploy/web/docker-compose.yml logs --tail=80 web
```

**回滚**：把 `ITTF_WEB_IMAGE` 改回上一个 tag，再 `pull + up -d`。所有历史版本在 ACR 里。

---

## 八、本地服务器：抓取 + 远程同步 + Sentry 监控

完整步骤详见 [`deploy/scraper/README.md`](../deploy/scraper/README.md)。

### 8.1 数据流

```
本地服务器：
  cron (sentry-cli monitors run)
    └─► sync_to_server_a.sh
          ├─ python scripts/run_*.py 抓取 → JSON
          ├─ python scripts/db/import_*.py + tsx migrate.ts → 本地 SQLite
          ├─ sqlite3 .backup → 一致性快照
          └─ rsync → 服务器 A:
                ├─ data/db/ittf.incoming.db   (临时)
                ├─ data/rankings/             (覆盖)
                ├─ data/player_profiles/      (覆盖)
                ├─ data/player_avatars/       (覆盖)
                └─ data/matches_complete/     (覆盖)
          └─ ssh 服务器 A:
                ├─ stop web
                ├─ 备份当前 db 到 backups/
                ├─ mv ittf.incoming.db → ittf.db (原子)
                └─ start web
```

### 8.2 关键决策

- **本地完成所有抓取 + SQLite 写入**：服务器 A 完全不需要 Python 环境
- **`.backup` 而不是直接拷贝 ittf.db**：避免拷贝时 WAL 文件导致不一致
- **服务器 A 短暂停 web**：约 5 秒；保证文件 fd 切换干净，避免 SQLite 看到旧 inode
- **每次同步前自动备份旧 db**：`/opt/ittf/data/db/backups/`，30 天 rotate
- **Sentry Cron Monitor 包装外层**：忘记跑 / 跑挂 / 跑超时都会告警

### 8.3 Sentry Cron Monitor 配置

1. Sentry → **Crons → Add Monitor**
2. Slug：`ittf-data-sync`
3. Schedule：Crontab 表达式，例 `0 3 * * 1`（每周一凌晨 3 点）
4. Check-in Margin：30 分钟
5. Max Runtime：60 分钟
6. Failure Tolerance：0
7. 保存后无需复制任何 ID（用 slug 即可）

### 8.4 部署摘要

```bash
# 本地服务器
cd /local && git clone <repo-url> ittf && cd ittf
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium
ssh-keygen -t ed25519 -f ~/.ssh/ittf_deploy -N ''
ssh-copy-id -i ~/.ssh/ittf_deploy.pub deploy@serverA
curl -sL https://sentry.io/get-cli/ | bash

# 改配置
cp deploy/scraper/cron_with_sentry.sh.example deploy/scraper/cron_with_sentry.sh
chmod +x deploy/scraper/sync_to_server_a.sh deploy/scraper/cron_with_sentry.sh
$EDITOR deploy/scraper/sync_to_server_a.sh   # 改 SERVER_A_HOST、LOCAL_PROJECT
$EDITOR deploy/scraper/cron_with_sentry.sh   # 填 SENTRY_AUTH_TOKEN / ORG / PROJECT

# 手动跑一次验证
./deploy/scraper/cron_with_sentry.sh

# 加 cron
crontab -e
# 0 3 * * 1 /local/ittf/deploy/scraper/cron_with_sentry.sh >> /local/ittf/scripts/logs/cron.log 2>&1
```

---

## 九、自定义事件埋点用法

### 全局点击（已自动）
任意 `<a> / <button> / [role="button"]` 点击都会上报，事件名形如 `click_link_internal` / `click_button`。

### 显式声明（推荐用于关键交互）
```tsx
<button data-track="ranking_sort" data-track-label="by_winrate">按胜率排序</button>
```

### 主动调用
```tsx
import { trackEvent } from '@/lib/analytics/umami';
trackEvent('player_view', { slug: player.slug, source: 'ranking_list' });
```

### 排除某个元素
```tsx
<button data-track-ignore>不需要统计的按钮</button>
```

---

## 十、上线验证清单

打开 `https://ittf.your-domain.com`，DevTools → Network：

- [ ] 主页 200，HTML 正确返回
- [ ] `https://analytics.your-domain.com/script.js` → 200
- [ ] 切路由 → `POST /api/send` 200
- [ ] `https://www.clarity.ms/tag/<id>` → 200
- [ ] Umami 后台 Realtime 面板看到自己的访问
- [ ] 点按钮 → Umami Events 列表出现 `click_*`
- [ ] Sentry 测试：临时 `throw new Error('sentry-test')` → Issues 收到
- [ ] 邮箱验证码：`/auth` 发送 → 邮箱收到
- [ ] 登录或注册后响应头里的 `Set-Cookie` 包含 `Secure`、`HttpOnly`、`SameSite=Lax`
- [ ] 响应头存在 `Content-Security-Policy`、`X-Content-Type-Options`、`Referrer-Policy`、`X-Frame-Options`、`Permissions-Policy`
- [ ] 从第三方站点或伪造 `Origin` 发起认证类 `POST` 请求会被 403 拒绝
- [ ] 直接访问服务器 A 的源站 IP 或未走 Cloudflare 的入口时，请求被拦截或无法正常使用
- [ ] Cloudflare Security Events 里能看到认证接口的 challenge / rate limit 测试记录
- [ ] 首次跑 cron：`./cron_with_sentry.sh` → Sentry Crons → ittf-data-sync 显示绿色 OK
- [ ] cron 跑完：服务器 A `/opt/ittf/data/db/ittf.db` 时间戳更新，`backups/` 有旧版

---

## 十一、运维手册

### 11.1 日志查看

| 位置 | 命令 |
|------|------|
| 服务器 A 容器 | `docker compose -f /opt/ittf/deploy/web/docker-compose.yml logs --tail=200 -f web` |
| 服务器 A nginx | `sudo tail -f /var/log/nginx/{error,access}.log` |
| 服务器 B 容器 | `docker compose -f /opt/umami/docker-compose.yml logs -f` |
| 本地 cron | `tail -f /local/ittf/scripts/logs/cron.log` |
| Sentry | `https://sentry.io` Issues / Performance / Crons |
| Umami | `https://analytics.your-domain.com` Realtime / Events |
| Clarity | `https://clarity.microsoft.com` Recordings / Heatmaps |

### 11.2 升级 Umami

```bash
ssh user@serverB
cd /opt/umami
docker compose pull
docker compose up -d
```

### 11.3 备份策略

| 数据 | 频率 | 方式 |
|------|------|------|
| 服务器 A SQLite | 每次 cron 自动 | `data/db/backups/` 30 天 rotate（sync_to_server_a.sh 已包含） |
| 服务器 A SQLite 异地 | 每周 | scp `backups/` 到对象存储 |
| 服务器 B Umami PG | 每日 | `pg_dump` 见 `deploy/umami/README.md` |
| 抓取产物 JSON | 不必备份 | 可重新抓取 |
| ACR 镜像 | 自动 | 阿里云保留所有 push 过的 tag |

### 11.4 故障恢复

**Web 容器起不来**
```bash
docker compose -f /opt/ittf/deploy/web/docker-compose.yml logs web
# 常见：.env 缺值 / SQLite 不存在 / 端口被占
```

**SQLite 损坏**
```bash
docker compose -f /opt/ittf/deploy/web/docker-compose.yml stop web
ls -t /opt/ittf/data/db/backups/ | head
cp /opt/ittf/data/db/backups/ittf-YYYYMMDD_HHMMSS.db /opt/ittf/data/db/ittf.db
docker compose -f /opt/ittf/deploy/web/docker-compose.yml start web
```

**Sentry Cron 一直报错**
- Sentry → Crons → 看最近一次 check-in 的 stderr
- 本地：`tail -f /local/ittf/scripts/logs/cron.log`
- 常见：网络失败 / playwright 浏览器升级后挂掉 / SSH key 过期

**镜像 pull 失败 401**
- ACR 登录态过期：`docker login crpi-...` 重登
- 阿里云个人版凭证有效期：登录后会一直有效，但更换密码后需重登

**回滚到上一个版本**
```bash
ssh deploy@serverA
sed -i 's|ITTF_WEB_IMAGE=.*|ITTF_WEB_IMAGE=crpi-...:<上一个 tag>|' /opt/ittf/deploy/web/.env
cd /opt/ittf
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env pull web
docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env up -d
```

---

## 十二、常见疑问（FAQ）

**Q: 浏览器跨域请求服务器 B 的 `/api/send` 会被 CORS 拦吗？**
不会。Umami 默认 `Access-Control-Allow-Origin: *`。CSP 的 `connect-src` 也已自动加白名单（`web/next.config.ts` 的 `buildCsp()` 根据 `NEXT_PUBLIC_UMAMI_URL` 自动生成）。

**Q: 为什么部署文档现在默认建议接 Cloudflare？**
因为当前生产安全配置已经包含三层假设：
- 浏览器侧：CSP、安全响应头、`Secure` Cookie
- 应用侧：认证类 `POST` 的同源校验、源站限流、受信任代理 IP 识别
- 边缘侧：WAF、Bot、防刷、源站隐藏

如果只做 Nginx 反代但不接 Cloudflare 或同级别边缘防护，应用层仍能工作，但认证接口的抗滥用能力会明显弱一截。

**Q: 服务器 B 挂了会影响主站吗？**
不会。`<script src>` 加载失败浏览器静默跳过，业务功能不受影响；事件丢失不影响数据正确性。

**Q: 本地服务器挂了多久能容忍？**
SQLite 数据库本身在服务器 A 上，挂多久网站都能正常服务，只是数据不更新。Sentry Cron Monitor 会在错过 check-in 后告警，告警阈值（Margin）建议设 30 分钟。

**Q: SENTRY_AUTH_TOKEN 怎么传给镜像 build 才安全？**
本仓库用 **BuildKit `--mount=type=secret`**，不是 `--build-arg`。区别在于：

| 方式 | 留痕位置 | 谁能看到 |
|------|---------|---------|
| `--build-arg`（**不要用**） | 镜像每层、`docker history`、`docker inspect` | 任何能 pull 镜像的人 |
| `--mount=type=secret`（**已采用**） | 仅在单个 RUN 步骤的 tmpfs 内，build 完销毁 | 没人 |

具体实现：`Dockerfile` 里 `RUN --mount=type=secret,id=sentry_auth_token,env=SENTRY_AUTH_TOKEN npm run build`。
build-and-push.sh 通过 `--secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN` 把宿主进程的 `SENTRY_AUTH_TOKEN` 环境变量挂进去。
`docker compose` 里的 `secrets:` 配置仅用于**本地 build compose 文件时**把宿主环境变量映射成 BuildKit secret；生产环境从 ACR 直接 `pull` 镜像时，不会再参与镜像构建。

需要 BuildKit 启用，docker 20.10+ 与 compose v2 默认即开。

**Q: 那其他 `--build-arg` 里的变量（NEXT_PUBLIC_*、SENTRY_ORG 等）泄露在镜像里安全吗？**
这些都是**公开标识符**，设计上就会出现在客户端 bundle 或 Sentry 上传请求里——
- `NEXT_PUBLIC_SENTRY_DSN` / `NEXT_PUBLIC_UMAMI_*` / `NEXT_PUBLIC_CLARITY_*`：浏览器端必需
- `SENTRY_ORG` / `SENTRY_PROJECT`：组织/项目 slug，仅是 URL 路径标识

它们被嵌入镜像与 docker history 是**预期的**，没有泄露风险。真正的密钥（SMTP_PASS 运行时注入、SENTRY_AUTH_TOKEN 走 secret mount、数据库密码）从不进镜像。

**Q: NEXT_PUBLIC_* 变量泄露在客户端 bundle 里安全吗？**
预期行为。这些都是公开标识符（DSN、Site ID），Sentry / Umami 设计就是要在浏览器里使用。真正的密钥（`SMTP_PASS`、`SENTRY_AUTH_TOKEN`、数据库密码）只在服务端，不会进 bundle。

**Q: 为什么 sync 时要停 5 秒 web？不能热替换 SQLite 吗？**
SQLite 在 WAL 模式下有 `.db-wal` 和 `.db-shm` 边带文件，且 Web 进程持有的 fd 指向旧 inode。`mv` 后旧进程仍读旧 inode（被 unlink 但不释放），新进程读新 inode，数据会"看起来不一致"。最干净的做法就是 stop → mv → start，5 秒可接受。

---

## 十三、相关文件索引

| 路径 | 作用 |
|------|------|
| **服务器 A（Web 应用）** | |
| `deploy/web/Dockerfile` | 镜像构建 |
| `deploy/web/docker-compose.yml` | 服务编排（image 可参数化） |
| `deploy/web/.env.example` | 环境变量模板 |
| `deploy/web/.dockerignore` | 镜像构建排除项 |
| `deploy/web/nginx.conf.example` | nginx 反代模板 |
| `deploy/web/build-and-push.sh` | 开发机构建并推送到 ACR |
| **服务器 B（Umami）** | |
| `deploy/umami/docker-compose.yml` | Umami + 专用 PG 编排 |
| `deploy/umami/.env.example` | 环境变量模板 |
| `deploy/umami/nginx.conf.example` | nginx 反代模板 |
| `deploy/umami/README.md` | 完整 runbook |
| **本地服务器（抓取）** | |
| `deploy/scraper/sync_to_server_a.sh` | 抓取 + 同步主脚本 |
| `deploy/scraper/cron_with_sentry.sh.example` | Sentry Cron 包装模板 |
| `deploy/scraper/README.md` | 完整 runbook |
| **前端代码** | |
| `web/lib/analytics/umami.ts` | 埋点封装 |
| `web/components/Analytics.tsx` | Umami SDK + Clarity + 全站点击代理 |
| `web/instrumentation-client.ts` | 浏览器侧 Sentry 初始化与路由切换埋点 |
| `web/sentry.server.config.ts` / `web/sentry.edge.config.ts` | 服务端与 Edge 侧 Sentry 初始化 |
| `web/instrumentation.ts` | Next.js 15 instrumentation 入口 |
| `web/app/global-error.tsx` | App Router 错误兜底 |
| `web/next.config.ts` | 含自动 CSP 生成（buildCsp）与安全响应头 |
