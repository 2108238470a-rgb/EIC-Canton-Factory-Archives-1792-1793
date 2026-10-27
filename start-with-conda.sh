#!/bin/bash
# OCR 文献翻译平台 — 一键启动脚本 (使用 conda 环境)
# 启动 Docker 依赖(PostgreSQL + Redis) + 后端(FastAPI + Celery) + 前端(Next.js)

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
CONDA_ENV="pdf2cn"

# 清除代理，避免本地服务通信被代理拦截
unset HTTP_PROXY
unset HTTPS_PROXY
unset ALL_PROXY
unset http_proxy
unset https_proxy
unset all_proxy

echo "========================================="
echo "  OCR 文献翻译平台 — 启动中"
echo "  使用 conda 环境: $CONDA_ENV"
echo "========================================="
echo ""

# 检查conda环境是否存在
if ! conda env list | grep -q "$CONDA_ENV"; then
    echo "❌ 错误: conda 环境 '$CONDA_ENV' 不存在"
    echo "请运行以下命令创建环境:"
    echo "  conda create -n $CONDA_ENV python=3.10"
    echo "  conda activate $CONDA_ENV"
    echo "  cd backend && pip install -r requirements.txt"
    exit 1
fi

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

# --- 2. 初始化数据库 ---
echo "[2/5] 初始化数据库 (pgvector + migrations)..."
cd "$BACKEND_DIR"
if conda run -n "$CONDA_ENV" --no-capture-output python scripts/init_db.py; then
    echo "      ✓ 数据库初始化成功"
else
    echo "      ❌ 数据库初始化失败"
    exit 1
fi
echo ""

# --- 3. 后端 FastAPI ---
echo "[3/5] 启动后端 FastAPI 服务..."

# 检查端口 8000 是否被占用
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "      ⚠️  端口 8000 已被占用，正在停止旧进程..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

conda run -n "$CONDA_ENV" --no-capture-output python -m app.main &
BACKEND_PID=$!
echo "      ✓ FastAPI 启动中 (PID: $BACKEND_PID, http://localhost:8000)"
echo ""

# 等待后端启动
echo "      等待后端就绪..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "      ✓ 后端 API 就绪"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "      ⚠️  后端启动超时，请检查日志"
    fi
    sleep 1
done
echo ""

# --- 4. Celery Worker ---
echo "[4/5] 启动 Celery Worker..."
cd "$BACKEND_DIR"
conda run -n "$CONDA_ENV" --no-capture-output celery -A app.tasks.celery_app worker --loglevel=info &
CELERY_PID=$!
echo "      ✓ Celery Worker 启动中 (PID: $CELERY_PID)"
echo ""

# --- 5. 前端 Next.js ---
echo "[5/5] 启动前端 Next.js..."

# 检查端口 3000 和 3001 是否被占用
if lsof -ti:3000 > /dev/null 2>&1; then
    echo "      ⚠️  端口 3000 已被占用，正在停止旧进程..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null
    sleep 1
fi

if lsof -ti:3001 > /dev/null 2>&1; then
    echo "      ⚠️  端口 3001 已被占用，正在停止旧进程..."
    lsof -ti:3001 | xargs kill -9 2>/dev/null
    sleep 1
fi

cd "$FRONTEND_DIR"
npm run dev > /tmp/nextjs.log 2>&1 &
FRONTEND_PID=$!

# 等待并检测实际使用的端口
echo "      ✓ Next.js 启动中 (PID: $FRONTEND_PID)"
sleep 3

FRONTEND_PORT=""
if lsof -ti:3000 > /dev/null 2>&1; then
    FRONTEND_PORT="3000"
elif lsof -ti:3001 > /dev/null 2>&1; then
    FRONTEND_PORT="3001"
fi

if [ -n "$FRONTEND_PORT" ]; then
    echo "      ✓ Next.js 就绪 (http://localhost:$FRONTEND_PORT)"
else
    echo "      ⚠️  无法检测到 Next.js 端口，请查看日志: /tmp/nextjs.log"
fi
echo ""

# --- 启动完成 ---
echo "========================================="
echo "  全部服务已启动"
echo "========================================="
echo ""
if [ -n "$FRONTEND_PORT" ]; then
    echo "  前端:     http://localhost:$FRONTEND_PORT"
else
    echo "  前端:     启动中，请检查 /tmp/nextjs.log"
fi
echo "  后端 API: http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "  或运行: ./stop-services.sh"
echo "========================================="

# 捕获 Ctrl+C，优雅退出
cleanup() {
    echo ""
    echo "正在停止所有服务..."
    kill $FRONTEND_PID 2>/dev/null || true
    kill $CELERY_PID 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    docker-compose -f "$PROJECT_DIR/docker-compose.yml" stop
    echo "全部服务已停止。"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待任意子进程退出
wait
