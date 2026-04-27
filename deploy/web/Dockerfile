# 服务器 A 上 Next.js Web 应用的镜像
#
# 关键点：
# 1. 用 bookworm-slim（glibc）作为运行时，better-sqlite3 的 prebuilt 二进制可直接使用
# 2. 多阶段构建：deps → build → runner，最终镜像不含编译器和 dev 依赖
# 3. 容器内目录与仓库保持一致：/app/web 是运行目录，data/ 在 /app/data（宿主卷挂载）
# 4. SENTRY_AUTH_TOKEN 走 BuildKit --mount=type=secret，绝不写进任何镜像层；
#    需要 DOCKER_BUILDKIT=1（docker 20.10+ 与 compose v2 已默认开启）
#
# 构建上下文应该是仓库根目录（不是 web/），因为镜像需要把 scripts/db/schema.sql 也拷进来。

# ---------- 1. 安装依赖 ----------
FROM docker.m.daocloud.io/library/node:20.18.1-bookworm-slim AS deps
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

# ---------- 2. 构建 ----------
FROM docker.m.daocloud.io/library/node:20.18.1-bookworm-slim AS builder
WORKDIR /app/web
ENV NEXT_TELEMETRY_DISABLED=1
# build 阶段把公开变量内联进 bundle / 镜像 ENV（NEXT_PUBLIC_* 走客户端，ORG/PROJECT 只是标识符）
ARG NEXT_PUBLIC_UMAMI_URL
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID
ARG NEXT_PUBLIC_CLARITY_PROJECT_ID
ARG NEXT_PUBLIC_SENTRY_DSN
ARG NEXT_PUBLIC_SENTRY_ENV
ARG SENTRY_ORG
ARG SENTRY_PROJECT
# 注意：SENTRY_AUTH_TOKEN 故意不在这里出现。它通过 --mount=type=secret 在
# 单个 RUN 步骤里临时可读，build 完即销毁，不会出现在任何 layer 或 docker history 中。
ENV NEXT_PUBLIC_UMAMI_URL=$NEXT_PUBLIC_UMAMI_URL \
    NEXT_PUBLIC_UMAMI_WEBSITE_ID=$NEXT_PUBLIC_UMAMI_WEBSITE_ID \
    NEXT_PUBLIC_CLARITY_PROJECT_ID=$NEXT_PUBLIC_CLARITY_PROJECT_ID \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_SENTRY_ENV=$NEXT_PUBLIC_SENTRY_ENV \
    SENTRY_ORG=$SENTRY_ORG \
    SENTRY_PROJECT=$SENTRY_PROJECT
COPY --from=deps /app/web/node_modules ./node_modules
COPY web/ ./
# secret mount：token 只以临时文件形式挂载在 /run/secrets 下，不进入镜像层
RUN --mount=type=secret,id=sentry_auth_token \
    /bin/sh -lc 'if [ -f /run/secrets/sentry_auth_token ]; then export SENTRY_AUTH_TOKEN="$(cat /run/secrets/sentry_auth_token)"; fi; npm run build'

# ---------- 3. 运行时 ----------
FROM docker.m.daocloud.io/library/node:20.18.1-bookworm-slim AS runner
WORKDIR /app/web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Next.js standalone 输出：server.js + 经 output file tracing 裁剪过的 node_modules
# 都在 .next/standalone/ 里。public 与 .next/static 不在 standalone 内，需另行拷贝。
COPY --from=builder /app/web/.next/standalone ./
COPY --from=builder /app/web/.next/static ./.next/static
COPY --from=builder /app/web/public ./public
# Schema 文件用于首次 db:migrate（路径与 web/lib/paths.ts 中 SCHEMA_FILE 对齐）
COPY scripts/db /app/scripts/db
EXPOSE 3000
# standalone 自带 server.js，直接 node 启动，不再需要 npm / next CLI
CMD ["node", "server.js"]
