# pgvector 扩展问题修复总结

## 问题根源

**错误信息**：
```
psycopg.errors.UndefinedObject: type "vector" does not exist
LINE 10: embedding VECTOR(1536)
```

**根本原因**：
1. Docker Compose 使用的 `postgres:15-alpine` 镜像不包含 pgvector 扩展
2. `backend/app/main.py:60` 使用 `Base.metadata.create_all()` 直接创建表，绕过了 Alembic 迁移
3. 虽然 Alembic 迁移文件包含 `CREATE EXTENSION vector`，但从未执行

## 修复方案

### 1. 更换 PostgreSQL 镜像（最小改动）

**文件**: `docker-compose.yml`

**修改前**:
```yaml
postgres:
  image: postgres:15-alpine
```

**修改后**:
```yaml
postgres:
  image: pgvector/pgvector:pg15
```

**说明**:
- 使用官方 pgvector 镜像，内置 pgvector 扩展
- 保持 PostgreSQL 15 版本一致
- 不影响现有数据（数据存储在 Docker volume 中）

### 2. 修改数据库初始化流程

**文件**: `backend/app/main.py`

**主要改动**:

#### a) 新增 pgvector 扩展启用函数
```python
def _ensure_pgvector_extension() -> None:
    """Ensure pgvector extension is enabled before any table operations."""
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension enabled")
    except Exception as e:
        logger.warning(f"Could not enable pgvector extension: {e}")
```

#### b) 新增 Alembic 迁移执行函数
```python
def _run_migrations() -> None:
    """Run Alembic migrations programmatically."""
    try:
        from alembic.config import Config
        from alembic import command
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))

        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.warning(f"Migration failed, falling back to create_all: {e}")
        # Fallback to create_all for tables not managed by migrations
        Base.metadata.create_all(bind=engine)
```

#### c) 修改启动流程
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting OCR Platform API...")

    # 1. 先启用 pgvector 扩展
    _ensure_pgvector_extension()

    # 2. 运行 Alembic 迁移（不再直接 create_all）
    _run_migrations()

    # 3. 应用兼容性补丁
    _ensure_schema_compatibility()
    logger.info("Database schema initialized")

    # 4. 确保存储目录存在
    ensure_directories()
    logger.info("Storage directories initialized")

    yield
```

### 3. 新增独立数据库初始化脚本

**文件**: `backend/scripts/init_db.py`

**功能**:
- 等待数据库就绪（最多 30 次重试）
- 启用 pgvector 扩展
- 运行所有 Alembic 迁移
- 详细的错误报告和状态日志

**使用方法**:
```bash
cd backend
conda run -n pdf2cn python scripts/init_db.py
```

### 4. 更新启动脚本

**文件**: `start-with-conda.sh`

**修改**: 在启动后端前增加数据库初始化步骤

```bash
# --- 2. 初始化数据库 ---
echo "[2/5] 初始化数据库 (pgvector + migrations)..."
cd "$BACKEND_DIR"
if conda run -n "$CONDA_ENV" --no-capture-output python scripts/init_db.py; then
    echo "      ✓ 数据库初始化成功"
else
    echo "      ❌ 数据库初始化失败"
    exit 1
fi
```

## 修改文件清单

1. ✅ `docker-compose.yml` - 更换为 pgvector 镜像
2. ✅ `backend/app/main.py` - 添加 pgvector 启用和迁移执行逻辑
3. ✅ `backend/scripts/init_db.py` - 新增独立初始化脚本
4. ✅ `start-with-conda.sh` - 增加数据库初始化步骤

## 验证步骤

### 1. 重启 Docker 服务（不会丢失数据）
```bash
docker-compose down
docker-compose up -d
```

### 2. 等待数据库就绪
```bash
until docker exec ocr_postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo "等待 PostgreSQL..."
    sleep 2
done
```

### 3. 验证 pgvector 扩展
```bash
docker exec ocr_postgres psql -U postgres -d ocr_platform -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

**预期输出**:
```
 extname | extversion
---------+------------
 vector  | 0.5.1
```

### 4. 手动运行数据库初始化（测试）
```bash
cd backend
conda run -n pdf2cn python scripts/init_db.py
```

### 5. 使用更新后的启动脚本
```bash
./start-with-conda.sh
```

### 6. 验证后端启动成功
```bash
curl http://localhost:8000/health
```

**预期输出**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected"
}
```

### 7. 验证 API 文档可访问
浏览器访问: http://localhost:8000/docs

### 8. 检查数据库表是否创建
```bash
docker exec ocr_postgres psql -U postgres -d ocr_platform -c "\dt"
```

**预期**: 应该看到所有表，包括：
- documents, pages, blocks, tasks, exports（原有）
- archival_metadata, source_units, entities, events 等（新增知识图谱表）
- search_chunks（包含 VECTOR 列）

### 9. 特别验证 search_chunks 表的 VECTOR 列
```bash
docker exec ocr_postgres psql -U postgres -d ocr_platform -c "\d search_chunks"
```

**预期**: 应该看到 `embedding` 列类型为 `vector(1536)`

## 安全保证

### ✅ 不会丢失数据
- Docker volume `postgres_data` 保持不变
- 只更换镜像，不删除 volume
- Alembic 迁移是增量的，不会删除现有数据

### ✅ 向后兼容
- 保留了 `create_all()` fallback 机制
- 保留了 `_ensure_schema_compatibility()` 补丁函数
- 原有 OCR、LLM、RAG 功能不受影响

### ⚠️ 注意事项
- 首次运行可能需要几秒钟等待 Alembic 迁移完成
- 如果迁移失败，会自动 fallback 到 `create_all()`
- 建议在生产环境使用前先备份数据库：
  ```bash
  docker exec ocr_postgres pg_dump -U postgres ocr_platform > backup.sql
  ```

## 故障排除

### 问题 1: pgvector 扩展仍然不可用
**解决方案**:
```bash
# 手动连接数据库并启用扩展
docker exec -it ocr_postgres psql -U postgres -d ocr_platform
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

### 问题 2: Alembic 迁移失败
**解决方案**:
```bash
# 查看当前迁移状态
cd backend
conda run -n pdf2cn alembic current

# 手动运行迁移
conda run -n pdf2cn alembic upgrade head
```

### 问题 3: 表已存在冲突
**解决方案**:
```bash
# 标记当前数据库状态为已迁移
cd backend
conda run -n pdf2cn alembic stamp head
```

## 后续建议

1. **生产部署**: 使用独立的迁移步骤，不在应用启动时运行迁移
2. **CI/CD**: 在 Docker 构建时运行 `init_db.py` 脚本
3. **监控**: 添加 pgvector 扩展版本检查
4. **备份**: 定期备份 PostgreSQL 数据

## 参考文档

- [pgvector 官方文档](https://github.com/pgvector/pgvector)
- [pgvector Docker 镜像](https://hub.docker.com/r/pgvector/pgvector)
- [Alembic 文档](https://alembic.sqlalchemy.org/)
- [SQLAlchemy pgvector 集成](https://github.com/pgvector/pgvector-python)

---

## 验证结果 ✅

所有修复已完成并验证成功：

1. **PostgreSQL 容器** - 使用 pgvector/pgvector:pg15 镜像，状态 healthy
2. **Redis 容器** - 状态 healthy
3. **pgvector 扩展** - 版本 0.8.7，已成功启用
4. **数据库表** - 23 张表全部创建成功，包括 `search_chunks` 表及其 `vector(1536)` 列
5. **后端服务** - 成功启动，监听 8000 端口
6. **健康检查** - `GET /health` 返回正常
7. **API 文档** - `GET /docs` 可正常访问

### 容器状态
```
CONTAINER ID   IMAGE                    STATUS
b9050ca861f8   redis:7-alpine           Up (healthy)
2939c118df1c   pgvector/pgvector:pg15   Up (healthy)
```

### pgvector 扩展信息
```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
 extname | extversion
---------+------------
 vector  | 0.8.7
```

### 后端健康检查
```json
{"status":"healthy","ocr_model":"PaddleOCR-VL-1.6","ocr_endpoint":"http://172.18.15.244:8888/layout-parsing"}
```

### 启动命令
```bash
# 启动所有服务（数据库 + 后端）
./start-with-conda.sh
```
