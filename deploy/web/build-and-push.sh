#!/usr/bin/env bash
#
# 构建 ITTF Web 镜像并推送到阿里云 ACR
#
# 用法：
#   ./deploy/web/build-and-push.sh             # 用 git short sha 作 tag
#   ./deploy/web/build-and-push.sh v1.2.3      # 自定义 tag
#
# 前置条件：
#   1. 已运行 docker login crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
#      (账号是阿里云用户名，密码在 ACR 控制台「访问凭证」里设置)
#   2. deploy/web/.env 已填好 NEXT_PUBLIC_* 等变量（会被内联进 bundle）

set -euo pipefail

REGISTRY=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
NAMESPACE=doubao_tt
REPO=doubao_web
IMAGE="${REGISTRY}/${NAMESPACE}/${REPO}"

# 解析 tag
if [ "$#" -ge 1 ]; then
    TAG="$1"
else
    if git rev-parse --short HEAD > /dev/null 2>&1; then
        TAG="$(git rev-parse --short HEAD)"
    else
        TAG="$(date +%Y%m%d-%H%M%S)"
    fi
fi

# 跳到仓库根
cd "$(dirname "$0")/../.."
ROOT_DIR="$(pwd)"

ENV_FILE="${ROOT_DIR}/deploy/web/.env"
if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: ${ENV_FILE} 不存在，先 cp deploy/web/.env.example deploy/web/.env 并填值" >&2
    exit 1
fi

# 加载 .env（用 set -a 让所有变量自动 export）
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

echo "==> 构建镜像 ${IMAGE}:${TAG}"
# 强制启用 BuildKit；compose v2 与 docker 20.10+ 默认开，这里写出来更显式
export DOCKER_BUILDKIT=1
docker build \
    -f deploy/web/Dockerfile \
    -t "${IMAGE}:${TAG}" \
    -t "${IMAGE}:latest" \
    --build-arg NEXT_PUBLIC_UMAMI_URL="${NEXT_PUBLIC_UMAMI_URL:-}" \
    --build-arg NEXT_PUBLIC_UMAMI_WEBSITE_ID="${NEXT_PUBLIC_UMAMI_WEBSITE_ID:-}" \
    --build-arg NEXT_PUBLIC_CLARITY_PROJECT_ID="${NEXT_PUBLIC_CLARITY_PROJECT_ID:-}" \
    --build-arg NEXT_PUBLIC_SENTRY_DSN="${NEXT_PUBLIC_SENTRY_DSN:-}" \
    --build-arg NEXT_PUBLIC_SENTRY_ENV="${NEXT_PUBLIC_SENTRY_ENV:-production}" \
    --build-arg SENTRY_ORG="${SENTRY_ORG:-}" \
    --build-arg SENTRY_PROJECT="${SENTRY_PROJECT:-}" \
    --secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN \
    .

echo "==> 推送 ${IMAGE}:${TAG}"
docker push "${IMAGE}:${TAG}"
docker push "${IMAGE}:latest"

echo ""
echo "✓ 构建完成: ${IMAGE}:${TAG}"
echo ""
echo "在服务器 A 上更新版本："
echo "  ssh deploy@serverA"
echo "  cd /opt/ittf"
echo "  # 修改 deploy/web/.env：ITTF_WEB_IMAGE=${IMAGE}:${TAG}"
echo "  docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env pull web"
echo "  docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env up -d"
