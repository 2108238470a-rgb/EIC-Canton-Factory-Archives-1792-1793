# 后端启动问题修复说明

## 问题汇总

### 1. 缺少 Python 依赖
**错误信息**: `ModuleNotFoundError: No module named 'sqlalchemy'` 和 `ModuleNotFoundError: No module named 'pgvector'`

**原因**: 新添加的知识工作台功能需要以下依赖：
- `sqlalchemy` - ORM框架
- `pgvector` - PostgreSQL向量扩展支持
- `alembic` - 数据库迁移工具

**解决方案**: 运行以下命令安装所有依赖
```bash
cd backend
pip install -r requirements.txt
```

### 2. 数据库迁移未运行
**症状**: 历史数据不见了，无法访问文档

**原因**:
- 新添加的知识工作台功能创建了大量新表
- Alembic迁移系统尚未初始化
- 现有的数据库表（documents, pages, blocks, tasks, exports）需要被标记为基线

**解决方案**: 运行数据库迁移
```bash
cd backend

# 方式1: 使用自动化脚本（推荐）
./setup.sh

# 方式2: 手动执行迁移
alembic stamp 000_initial     # 标记现有表为基线
alembic upgrade head          # 应用所有新迁移
```

### 3. 后端服务未启动
**错误信息**: `Failed to proxy http://localhost:8000/api/documents... ECONNREFUSED`

**原因**: 前端在尝试连接后端API但后端服务没有运行

**解决方案**: 启动后端服务
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

## 已修复的代码问题

### 1. SQLAlchemy保留字段冲突
**位置**: `app/models/assertion.py:64`

**问题**: `metadata` 是SQLAlchemy的保留字段名，会导致模型定义失败

**修复**: 将字段重命名为 `extra_metadata`
```python
# 修改前
metadata = Column(JSON, nullable=True, comment="附加元数据")

# 修改后
extra_metadata = Column(JSON, nullable=True, comment="附加元数据")
```

## 快速启动指南

### 完整环境设置
```bash
# 1. 进入后端目录
cd backend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 确保PostgreSQL运行
# 检查数据库连接:
python -c "from sqlalchemy import create_engine; engine = create_engine('postgresql://postgres:postgres@localhost:5432/ocr_platform'); engine.connect()"

# 4. 运行数据库迁移
alembic stamp 000_initial
alembic upgrade head

# 5. 启动后端服务
uvicorn app.main:app --reload --port 8000
```

### 在另一个终端启动前端
```bash
cd frontend
npm run dev
```

## 新功能：知识工作台 2.0

已添加以下新表支持知识图谱功能：

### 档案元数据
- `archival_metadata` - 档案馆藏信息

### 语料管理
- `source_units` - 原文单元
- `source_unit_spans` - 原文片段
- `text_revisions` - 文本修订历史
- `evidence_spans` - 证据片段

### 实体识别
- `entities` - 实体（人物、地点、组织等）
- `entity_mentions` - 实体提及
- `identity_decisions` - 实体同一性决策

### 事件抽取
- `event_mentions` - 事件提及
- `events` - 事件
- `participations` - 事件参与

### 知识断言
- `assertions` - 结构化断言
- `assertion_evidence` - 断言证据
- `review_decisions` - 审核决策

### 系统支持
- `extraction_runs` - 抽取运行记录
- `search_chunks` - 向量搜索块

## 验证安装

运行以下命令检查所有表是否正确创建：

```bash
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('postgresql://postgres:postgres@localhost:5432/ocr_platform')
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\"))
    tables = [row[0] for row in result]
    print(f'共 {len(tables)} 个表:')
    for table in tables:
        print(f'  ✓ {table}')
"
```

预期输出应包含所有原有表和新表（共约20个表）。

## 故障排查

### 如果迁移失败
```bash
# 检查当前迁移状态
alembic current

# 查看迁移历史
alembic history

# 回滚最后一次迁移
alembic downgrade -1
```

### 如果数据库连接失败
1. 确认PostgreSQL正在运行
2. 检查数据库凭据（默认: postgres/postgres@localhost:5432/ocr_platform）
3. 确认数据库 `ocr_platform` 已创建

### 如果前端仍然报错
1. 确认后端在 http://localhost:8000 上运行
2. 访问 http://localhost:8000/docs 查看API文档
3. 检查浏览器控制台的详细错误信息
