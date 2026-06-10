# Umami 部署 (服务器 B)

## 一、前置条件

- 服务器 B 已安装 Docker 24+ 和 docker compose v2
- 已购买/绑定一个子域，例如 `analytics.your-domain.com`，DNS A 记录指向服务器 B 的公网 IP
- 服务器 B 安装了 nginx 和 certbot（`apt install nginx certbot python3-certbot-nginx`）
- 服务器 B 防火墙放行 80/443

## 二、首次部署

```bash
# 1. 把整个 deploy/umami 目录拷到服务器 B 的 /opt/umami（路径任意）
scp -r deploy/umami user@serverB:/opt/

# 2. 登录服务器 B，生成密钥
ssh user@serverB
cd /opt/umami
cp .env.example .env
echo "UMAMI_DB_PASSWORD=$(openssl rand -hex 24)" > .env
echo "UMAMI_APP_SECRET=$(openssl rand -hex 32)" >> .env
chmod 600 .env

# 3. 启动容器
docker compose up -d
docker compose logs -f umami       # 等待 "ready - started server on..." 后 Ctrl+C

# 4. 配置 nginx + 证书
sudo cp nginx.conf.example /etc/nginx/conf.d/umami.conf
sudo sed -i 's/analytics.example.com/analytics.your-domain.com/g' /etc/nginx/conf.d/umami.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d analytics.your-domain.com

# 5. 浏览器打开 https://analytics.your-domain.com
#    默认账号：admin / umami  ← 立即在 Settings → Profile 改密码！
```

## 三、添加站点拿 Website ID

1. 登录后台 → **Settings → Websites → Add website**
2. Name 填 `ittf-rankings`，Domain 填你前端的对外域名（如 `ittf.your-domain.com`）
3. 保存后页面会显示 **Website ID（UUID）**，复制下来

## 四、配置服务器 A 上的前端

在服务器 A 的 `web/.env.local`（或部署平台的环境变量）填：

```
NEXT_PUBLIC_UMAMI_URL=https://analytics.your-domain.com
NEXT_PUBLIC_UMAMI_WEBSITE_ID=粘贴上一步的 UUID
```

重新 build + 部署 Next.js（`NEXT_PUBLIC_*` 变量在 build 时被内联到 bundle）。

## 五、验证

打开线上前端，浏览器开发者工具 Network：

- `https://analytics.your-domain.com/script.js` → 200，约 6KB
- 切换路由后能看到 `POST /api/send` → 200
- Umami 后台 → Realtime 面板能看到自己的访问

## 六、运维

### 查看日志
```bash
cd /opt/umami
docker compose logs -f umami
docker compose logs -f umami-db
```

### 升级
```bash
cd /opt/umami
docker compose pull
docker compose up -d
```

### 备份
PostgreSQL 数据卷在 `umami-db-data`。每日定时备份脚本（可丢进 `/etc/cron.daily/umami-backup`）：

```bash
#!/bin/sh
set -e
BACKUP_DIR=/var/backups/umami
DATE=$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"
docker exec umami-db pg_dump -U umami umami | gzip > "$BACKUP_DIR/umami-$DATE.sql.gz"
# 保留最近 30 天
find "$BACKUP_DIR" -name 'umami-*.sql.gz' -mtime +30 -delete
```

### 恢复
```bash
gunzip -c umami-20260501.sql.gz | docker exec -i umami-db psql -U umami umami
```

### 资源占用
- 稳态：Umami ~150MB，PG ~80MB
- 已通过 docker compose 的 `deploy.resources.limits.memory` 各限制 512MB，留足余量给突发流量

## 七、安全小贴士

- `.env` 文件 chmod 600，绝不入库
- 默认 admin 密码必须立即修改
- 如果服务器 B 上还跑别的服务，建议给 Umami 的 nginx vhost 加 IP 白名单或 Basic Auth 限制后台 `/dashboard /settings`，仅放行 `/api/send`、`/script.js`、`/api/collect` 这些上报接口给所有人

可选的 nginx 加固示例（后台仅限办公网 IP）：

```nginx
location /api/send  { proxy_pass http://127.0.0.1:3001; }
location = /script.js { proxy_pass http://127.0.0.1:3001; }

location / {
    allow 1.2.3.4/32;     # 你的办公/家庭 IP
    deny  all;
    proxy_pass http://127.0.0.1:3001;
}
```
