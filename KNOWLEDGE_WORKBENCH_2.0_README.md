# 广州商馆档案历史知识工作台 2.0 - 开发说明

## 概述

本分支实现了历史知识工作台 2.0 的核心数据模型和基础架构，用于支持广州商馆档案（1792-1793）的数字化、标注、抽取、复核和知识图谱构建。

## 已完成工作

### 1. 数据库模型（18个新表）

#### 档案元数据与文书分段
- `archival_metadata` - 档案元数据（馆藏、档号、日期覆盖）
- `source_units` - 文书单元（信件、日记条目、报告等）
- `source_unit_spans` - 文书与块的映射关系
- `text_revisions` - 文本版本管理（不可变、带哈希）
- `evidence_spans` - 证据锚点（字符偏移、bbox、裁图）

#### 实体识别与身份链接
- `entities` - 规范实体（人物、机构、地点）
- `entity_mentions` - 实体提及（原文形式、尊称、职衔）
- `identity_decisions` - 身份判断决策（可撤销）

#### 事件与参与关系
- `events` - 历史事件（跨来源对齐）
- `event_mentions` - 事件叙述（单一来源）
- `participations` - 实体参与事件的角色
- `event_relations` - 事件间关系（回复、后续、因果）

#### 断言与证据
- `assertions` - 结构化断言（主谓宾三元组）
- `assertion_evidences` - 断言-证据关联（支持/反对）

#### 复核与追踪
- `review_decisions` - 人工复核决策（带版本）
- `extraction_runs` - 抽取任务记录（幂等性、成本追踪）

#### 检索支持
- `search_chunks` - 检索分块（pgvector向量 + 全文索引）

### 2. 技术特性

#### 证据溯源
- Web Annotation Model 风格的文本锚点
- 字符偏移（Unicode码点）+ 前后缀文本
- 页面坐标与裁图链接
- 多版本文本支持

#### 版本管理
- 文本修订不可变（content_hash）
- 决策可撤销（previous_decision_id）
- 抽取任务幂等键

#### 时间处理
- 起止日期区间
- 精度标记（年/月/日/约）
- 区分文书日期、事件日期、有效期

#### 关系分离
- 人物-机构任职关系作为断言，不是人物属性
- 共现 ≠ 历史关系
- 候选合并与确认合并分开

### 3. 依赖更新

添加了 `pgvector>=0.2.4` 用于向量检索支持。

### 4. 数据库迁移

创建了完整的 Alembic 迁移脚本：
- 启用 pgvector 扩展
- 创建所有18个新表
- 创建必要的索引和外键约束
- 支持回滚

## 下一步工作

### Phase 1: API 接口实现

1. **文档抽取接口**
   - `POST /documents/{id}/extractions` - 发起异步抽取
   - 候选实体/事件生成
   - 幂等性保证

2. **标注管理接口**
   - `GET /annotations` - 标注总表查询
   - `GET /entities/{id}` - 人物档案
   - `GET /events/{id}` - 事件详情
   - `GET /evidence/{id}` - 证据详情

3. **复核接口**
   - `POST /reviews` - 提交复核决策
   - 版本号防冲突
   - 字段级审核

4. **检索与问答**
   - `POST /search` - 混合检索（关键词 + 向量）
   - `POST /questions` - 带证据的问答
   - 引用链接生成

5. **知识图谱**
   - `GET /graph` - 子图查询
   - 节点：人物、事件、机构、地点
   - 边：参与、回复、后续、任职

6. **导出接口**
   - `POST /knowledge-exports` - CSV/JSON 导出
   - 16列用户标注表
   - 证据清单与裁图

### Phase 2: 前端界面

1. 标注总表（筛选、分页、复核状态）
2. 人物档案页面（别名、任职、参与事件）
3. 事件时间线
4. 证据问答界面
5. 关系图可视化
6. 审核队列

### Phase 3: 抽取流程

1. 文书分段（日期标题、会议条目、来函、复函）
2. 实体提及抽取（人名、机构、地点、日期）
3. 事件叙述抽取
4. 身份消歧与候选生成
5. 证据锚点回查
6. Schema 校验

### Phase 4: 检索优化

1. PostgreSQL 全文检索配置（中英文）
2. pgvector 索引优化
3. 混合检索评估
4. 缓存策略

## 运行迁移

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 运行迁移
alembic upgrade head

# 回滚（如需要）
alembic downgrade -1
```

## 设计参考

本实现参考了以下标准和最佳实践：
- [W3C Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [CIDOC CRM - Documenting Events](https://cidoc-crm.org/Resources/documenting-events)

## 验收标准

参见原设计文档第 8 节，包括：
- 证据可溯源性
- 版本可追踪性
- 复核可撤销性
- 冲突可检测性
- 无答案正确拒答

## 注意事项

1. **不要把候选当确认**：抽取结果进入候选区，需人工审核
2. **不要伪造证据**：外部来源须明确标记，不能伪装成档案原文
3. **不要过度推断**：同页出现 ≠ 历史关系，先发生 ≠ 导致
4. **不要覆盖人工**：人工批准内容不被重跑任务覆盖
5. **区分缺失原因**：未记载、字迹不清、多种候选，使用不同标记

## 联系

如有问题，请参考 `/docs/knowledge_workbench_2.0_spec.md` 完整设计文档。
