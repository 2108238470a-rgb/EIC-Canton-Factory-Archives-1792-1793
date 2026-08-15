# OCR 文献翻译平台

一个基于 PaddleOCR-VL 和 GPT 的历史文献 OCR 识别与翻译平台。

## 功能特性

- 上传 PDF 或图片文档
- 自动版面分析与 OCR 识别
- GPT 驱动的文本处理：
  - OCR 纠错
  - 现代英语重写
  - 中文翻译
- 可视化阅读器：原图 + bbox 叠加 + 文本面板
- 支持导出 JSON / Markdown / TXT

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- SQLAlchemy + PostgreSQL
- Celery + Redis
- PaddleOCR-VL (本地服务)
- OpenAI API

### 前端

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui

## 快速开始

> paddlex --serve   --pipeline PaddleOCR-VL-1.6      --port 8888
> paddlex --serve --pipeline PaddleOCR-VL --port 8888

如果需要把 ERNIEKit 微调后的历史英文手写体模型发布成服务，先阅读
[ERNIEKit 微调模型接入说明](docs/ERNIEKIT_SERVER_DEPLOYMENT.md)。项目仍通过
PaddleX 的完整 PaddleOCR-VL 流水线调用 `/layout-parsing`，ERNIEKit 不直接充当 HTTP 服务。

```
unset HTTP_PROXY
unset HTTPS_PROXY
unset ALL_PROXY
unset http_proxy
unset https_proxy
unset all_proxy
```

### 1. 启动依赖服务

```bash
# 启动 PostgreSQL 和 Redis
docker-compose up -d
```

### 2. 配置后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 复制环境变量配置
cp .env.example .env

# 编辑 .env 文件，配置：
# - DATABASE_URL
# - GPT_API_KEY
# - PADDLE_OCR_URL (确保 PaddleOCR 服务已启动)
```

### 3. 启动后端服务

```bash
# 终端 1: 启动 FastAPI
cd backend
source venv/bin/activate
python -m app.main

# 终端 2: 启动 Celery Worker
cd backend
source venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info
```

### 4. 配置前端

```bash
cd frontend

# 安装依赖
npm install

# 复制环境变量配置
cp .env.example .env.local
```

### 5. 启动前端

```bash
cd frontend
npm run dev
```

### 6. 访问应用

- 前端: http://localhost:3000
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- OCR 连通性: http://localhost:8000/health/ocr

## 项目结构

```
MVP_PaddleOCR/
├── backend/
│   ├── app/
│   │   ├── api/routers/     # API 路由
│   │   ├── models/          # 数据库模型
│   │   ├── schemas/         # Pydantic 模式
│   │   ├── services/        # 业务逻辑
│   │   ├── repositories/    # 数据访问层
│   │   ├── tasks/           # Celery 任务
│   │   ├── prompts/         # GPT 提示模板
│   │   ├── core/            # 核心模块
│   │   └── utils/           # 工具函数
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/             # Next.js 页面
│       ├── components/      # React 组件
│       ├── lib/             # API 客户端
│       └── types/           # TypeScript 类型
├── storage/                 # 文件存储
└── docker-compose.yml
```

## API 接口

### 文档管理

- `POST /api/documents/upload` - 上传文档
- `GET /api/documents` - 文档列表
- `GET /api/documents/{id}` - 文档详情
- `DELETE /api/documents/{id}` - 删除文档
- `POST /api/documents/{id}/run-ocr` - 启动 OCR

### 页面与区块

- `GET /api/documents/{id}/pages` - 获取页面列表
- `GET /api/pages/{id}` - 页面详情
- `GET /api/pages/{id}/blocks` - 获取区块列表
- `GET /api/blocks/{id}` - 区块详情
- `PATCH /api/blocks/{id}` - 更新区块

### GPT 处理

- `POST /api/blocks/{id}/run-polish` - 处理单个区块
- `POST /api/blocks/pages/{id}/run-polish` - 处理整页
- `POST /api/blocks/documents/{id}/run-polish` - 处理整个文档

### 导出

- `POST /api/exports/documents/{id}/export` - 创建导出
- `GET /api/exports/documents/{id}/exports` - 导出列表
- `GET /api/exports/{id}/download` - 下载导出文件

### 任务

- `GET /api/tasks/{id}` - 查询任务状态

## 环境变量

### 后端 (.env)

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ocr_platform
REDIS_URL=redis://localhost:6379/0
PADDLE_OCR_URL=http://127.0.0.1:8888/layout-parsing
PADDLE_OCR_MODEL_NAME=PaddleOCR-VL-0.9B-history-sft
PADDLE_OCR_MAX_CONCURRENCY=1
GPT_API_KEY=replace-with-your-api-key
GPT_BASE_URL=https://api.siliconflow.cn/v1
GPT_MODEL=deepseek-ai/DeepSeek-V3
```

### 前端 (.env.local)

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 注意事项

1. 确保 PaddleOCR-VL 服务已在 `http://127.0.0.1:8888` 启动；服务端部署见 `docs/ERNIEKIT_SERVER_DEPLOYMENT.md`
2. GPT API 需要有效的 API Key
3. 不要把真实 API Key 写入代码或提交到版本库；如曾提交，请立即撤销并重建
4. 大文件处理可能需要较长时间，请耐心等待
