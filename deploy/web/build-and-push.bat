@echo off
rem
rem Build ITTF Web image and push to Aliyun ACR (Windows batch version).
rem
rem Usage:
rem   deploy\web\build-and-push.bat            use git short sha as tag
rem   deploy\web\build-and-push.bat v1.2.3     use custom tag
rem
rem Prerequisites:
rem   1. docker login crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
rem      (username = Aliyun account, password from ACR console)
rem   2. deploy\web\.env is filled with NEXT_PUBLIC_* / SENTRY_AUTH_TOKEN, etc.
rem
rem NOTE: keep this file ASCII-only. Chinese Windows cmd.exe parses .bat as GBK,
rem and UTF-8 multi-byte sequences get misread, breaking if/for/rem blocks.
rem

setlocal enabledelayedexpansion

set "REGISTRY=crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com"
set "NAMESPACE=doubao_tt"
set "REPO=doubao_web"
set "IMAGE=%REGISTRY%/%NAMESPACE%/%REPO%"

rem ---- Resolve tag ----
if not "%~1"=="" (
    set "TAG=%~1"
) else (
    set "TAG="
    for /f "usebackq tokens=*" %%i in (`git rev-parse --short HEAD 2^>nul`) do set "TAG=%%i"
    if "!TAG!"=="" (
        for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "TAG=%%i"
    )
)

rem ---- cd to repo root (two levels above this script) ----
cd /d "%~dp0..\.."
set "ROOT_DIR=%CD%"

set "ENV_FILE=%ROOT_DIR%\deploy\web\.env"
if not exist "%ENV_FILE%" (
    echo ERROR: %ENV_FILE% not found. Copy deploy\web\.env.example to deploy\web\.env and fill in values. 1>&2
    exit /b 1
)

rem ---- Load .env (skip blank lines and lines starting with '#') ----
for /f "usebackq eol=# delims=" %%l in ("%ENV_FILE%") do set "%%l"

if "!NEXT_PUBLIC_SENTRY_ENV!"=="" set "NEXT_PUBLIC_SENTRY_ENV=production"

if "!SENTRY_AUTH_TOKEN!"=="" (
    echo WARN: SENTRY_AUTH_TOKEN is empty in .env, source map upload will be skipped. 1>&2
)

echo ==^> Building %IMAGE%:!TAG!
set "DOCKER_BUILDKIT=1"

docker build ^
    -f deploy/web/Dockerfile ^
    -t "%IMAGE%:!TAG!" ^
    -t "%IMAGE%:latest" ^
    --build-arg NEXT_PUBLIC_UMAMI_URL=!NEXT_PUBLIC_UMAMI_URL! ^
    --build-arg NEXT_PUBLIC_UMAMI_WEBSITE_ID=!NEXT_PUBLIC_UMAMI_WEBSITE_ID! ^
    --build-arg NEXT_PUBLIC_CLARITY_PROJECT_ID=!NEXT_PUBLIC_CLARITY_PROJECT_ID! ^
    --build-arg NEXT_PUBLIC_SENTRY_DSN=!NEXT_PUBLIC_SENTRY_DSN! ^
    --build-arg NEXT_PUBLIC_SENTRY_ENV=!NEXT_PUBLIC_SENTRY_ENV! ^
    --build-arg SENTRY_ORG=!SENTRY_ORG! ^
    --build-arg SENTRY_PROJECT=!SENTRY_PROJECT! ^
    --secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN ^
    .
if errorlevel 1 (
    echo BUILD FAILED 1>&2
    exit /b 1
)

echo ==^> Pushing %IMAGE%:!TAG!
docker push "%IMAGE%:!TAG!"
if errorlevel 1 exit /b 1
docker push "%IMAGE%:latest"
if errorlevel 1 exit /b 1

echo.
echo OK: built and pushed %IMAGE%:!TAG!
echo.
echo Next, on server A:
echo   ssh deploy@serverA
echo   cd /opt/ittf
echo   # edit deploy/web/.env: ITTF_WEB_IMAGE=%IMAGE%:!TAG!
echo   docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env pull web
echo   docker compose -f deploy/web/docker-compose.yml --env-file deploy/web/.env up -d

endlocal
