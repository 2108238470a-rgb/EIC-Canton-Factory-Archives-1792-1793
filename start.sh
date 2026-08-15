#!/bin/bash
# OCR 文献翻译平台 — 一键启动脚本
# 启动 Docker 依赖(PostgreSQL + Redis) + 后端(FastAPI + Celery) + 前端(Next.js)
# 不包括 PaddleOCR 模型服务器

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# 清除代理，避免本地服务通信被代理拦截
unset HTTP_PROXY
unset HTTPS_PROXY
unset ALL_PROXY
unset http_proxy
unset https_proxy
unset all_proxy

echo "========================================="
echo "  OCR 文献翻译平台 — 启动中"
echo "========================================="
echo ""

# --- 1. Docker 依赖服务 ---
echo "[1/4] 启动 Docker 依赖服务 (PostgreSQL + Redis)..."
docker-compose -f "$PROJECT_DIR/docker-compose.yml" up -d
echo "      等待服务就绪..."
sleep 3

# 检查 PostgreSQL
until docker exec ocr_postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo "      PostgreSQL 启动中..."
    sleep 2
done
echo "      ✓ PostgreSQL 就绪 (localhost:5432)"

# 检查 Redis
until docker exec ocr_redis redis-cli ping > /dev/null 2>&1; do
    echo "      Redis 启动中..."
    sleep 2
done
echo "      ✓ Redis 就绪 (localhost:6379)"
echo ""

# --- 2. 后端 FastAPI ---
echo "[2/4] 启动后端 FastAPI 服务..."
cd "$BACKEND_DIR"
python -m app.main &
BACKEND_PID=$!
echo "      ✓ FastAPI 启动中 (PID: $BACKEND_PID, http://localhost:8000)"
echo ""

# --- 3. Celery Worker ---
echo "[3/4] 启动 Celery Worker..."
cd "$BACKEND_DIR"
celery -A app.tasks.celery_app worker --loglevel=info &
CELERY_PID=$!
echo "      ✓ Celery Worker 启动中 (PID: $CELERY_PID)"
echo ""

# --- 4. 前端 Next.js ---
echo "[4/4] 启动前端 Next.js..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!
echo "      ✓ Next.js 启动中 (PID: $FRONTEND_PID, http://localhost:3000)"
echo ""

# --- 启动完成 ---
echo "========================================="
echo "  全部服务已启动"
echo "========================================="
echo ""
echo "  前端:     http://localhost:3000"
echo "  后端 API: http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "========================================="

# 捕获 Ctrl+C，优雅退出
cleanup() {
    echo ""
    echo "正在停止所有服务..."
    kill $FRONTEND_PID 2>/dev/null
    kill $CELERY_PID 2>/dev/null
    kill $BACKEND_PID 2>/dev/null
    docker-compose -f "$PROJECT_DIR/docker-compose.yml" stop
    echo "全部服务已停止。"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待任意子进程退出
wait
