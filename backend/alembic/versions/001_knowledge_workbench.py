"""Add knowledge workbench 2.0 models

Revision ID: 001_knowledge_workbench
Revises:
Create Date: 2026-10-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_knowledge_workbench'
down_revision = '000_initial'  # Depends on initial migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adopt tables created by pre-Alembic development builds. Existing tables are
    # reconciled by 003; missing tables still use the original definitions below.
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    def create_table(name, *args, **kwargs):
        if name not in existing_tables:
            op.create_table(name, *args, **kwargs)
    def create_index(name, table, *args, **kwargs):
        if name not in {i['name'] for i in sa.inspect(bind).get_indexes(table)}:
            op.create_index(name, table, *args, **kwargs)
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create archival_metadata table
    create_table('archival_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('repository', sa.String(length=255), nullable=True, comment='档案馆藏机构'),
        sa.Column('archival_reference', sa.String(length=255), nullable=True, comment='档号'),
        sa.Column('collection_name', sa.String(length=500), nullable=True, comment='卷名'),
        sa.Column('coverage_date_start', sa.Date(), nullable=True, comment='覆盖起始日期'),
        sa.Column('coverage_date_end', sa.Date(), nullable=True, comment='覆盖结束日期'),
        sa.Column('date_precision', sa.String(length=50), nullable=True, comment='日期精度：year/month/day'),
        sa.Column('completeness_status', sa.Enum('COMPLETE', 'PARTIAL', 'FRAGMENTED', 'UNKNOWN', name='completenessstatus'), server_default='UNKNOWN', comment='完整性状态'),
        sa.Column('completeness_notes', sa.Text(), nullable=True, comment='完整性说明'),
        sa.Column('original_language', sa.String(length=50), nullable=True, comment='原始语言'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id')
    )
    create_index(op.f('ix_archival_metadata_archival_reference'), 'archival_metadata', ['archival_reference'], unique=False)
    create_index(op.f('ix_archival_metadata_document_id'), 'archival_metadata', ['document_id'], unique=False)
    create_index(op.f('ix_archival_metadata_id'), 'archival_metadata', ['id'], unique=False)

    # Create source_units table
    create_table('source_units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('archival_metadata_id', sa.Integer(), nullable=False),
        sa.Column('unit_type', sa.Enum('LETTER_INCOMING', 'LETTER_OUTGOING', 'DIARY_ENTRY', 'MEETING_MINUTES', 'REPORT', 'ATTACHMENT', 'TITLE', 'OTHER', name='sourceunittype'), nullable=False, comment='文书类型'),
        sa.Column('title', sa.String(length=500), nullable=True, comment='标题'),
        sa.Column('sequence_number', sa.Integer(), nullable=True, comment='序号'),
        sa.Column('original_date_text', sa.String(length=255), nullable=True, comment='原文日期'),
        sa.Column('normalized_date_start', sa.Date(), nullable=True, comment='规范起始日期'),
        sa.Column('normalized_date_end', sa.Date(), nullable=True, comment='规范结束日期'),
        sa.Column('date_precision', sa.Enum('YEAR', 'MONTH', 'DAY', 'APPROXIMATE', 'UNKNOWN', name='dateprecision'), server_default='UNKNOWN', comment='日期精度'),
        sa.Column('date_basis', sa.Text(), nullable=True, comment='日期依据'),
        sa.Column('segmentation_status', sa.Enum('PENDING', 'APPROVED', 'NEEDS_REVIEW', 'REJECTED', name='segmentationstatus'), server_default='PENDING', comment='分段审核状态'),
        sa.Column('segmentation_notes', sa.Text(), nullable=True, comment='分段说明'),
        sa.Column('summary', sa.Text(), nullable=True, comment='内容摘要'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['archival_metadata_id'], ['archival_metadata.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_source_units_archival_metadata_id'), 'source_units', ['archival_metadata_id'], unique=False)
    create_index(op.f('ix_source_units_id'), 'source_units', ['id'], unique=False)
    create_index(op.f('ix_source_units_normalized_date_start'), 'source_units', ['normalized_date_start'], unique=False)

    # Create source_unit_spans table
    create_table('source_unit_spans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_unit_id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('reading_order', sa.Integer(), nullable=False, comment='阅读顺序'),
        sa.Column('char_start', sa.Integer(), nullable=True, comment='起始字符偏移（Unicode码点）'),
        sa.Column('char_end', sa.Integer(), nullable=True, comment='结束字符偏移（Unicode码点）'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_unit_id'], ['source_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_source_unit_spans_block_id'), 'source_unit_spans', ['block_id'], unique=False)
    create_index(op.f('ix_source_unit_spans_id'), 'source_unit_spans', ['id'], unique=False)
    create_index(op.f('ix_source_unit_spans_source_unit_id'), 'source_unit_spans', ['source_unit_id'], unique=False)

    # Create text_revisions table
    create_table('text_revisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('text_type', sa.Enum('OCR_RAW', 'OCR_CORRECTED', 'MODERN_ENGLISH', 'TRANSLATION_ZH', 'MANUAL_TRANSCRIPTION', name='texttype'), nullable=False, comment='文本种类'),
        sa.Column('content', sa.Text(), nullable=False, comment='不可变正文'),
        sa.Column('content_hash', sa.String(length=64), nullable=False, comment='内容hash'),
        sa.Column('previous_revision_id', sa.Integer(), nullable=True),
        sa.Column('revision_number', sa.Integer(), nullable=False, comment='版本号'),
        sa.Column('author', sa.String(length=255), nullable=True, comment='作者（用户或系统）'),
        sa.Column('author_type', sa.String(length=50), nullable=True, comment='作者类型：human/ai/ocr'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['previous_revision_id'], ['text_revisions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_text_revisions_block_id'), 'text_revisions', ['block_id'], unique=False)
    create_index(op.f('ix_text_revisions_content_hash'), 'text_revisions', ['content_hash'], unique=False)
    create_index(op.f('ix_text_revisions_created_at'), 'text_revisions', ['created_at'], unique=False)
    create_index(op.f('ix_text_revisions_id'), 'text_revisions', ['id'], unique=False)

    # Create evidence_spans table
    create_table('evidence_spans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text_revision_id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=True),
        sa.Column('char_start', sa.Integer(), nullable=True, comment='起始字符偏移'),
        sa.Column('char_end', sa.Integer(), nullable=True, comment='结束字符偏移'),
        sa.Column('exact_text', sa.Text(), nullable=True, comment='精确引句'),
        sa.Column('prefix_text', sa.String(length=100), nullable=True, comment='前缀文本'),
        sa.Column('suffix_text', sa.String(length=100), nullable=True, comment='后缀文本'),
        sa.Column('bbox', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='边界框 [x1, y1, x2, y2]'),
        sa.Column('image_width', sa.Integer(), nullable=True, comment='图像宽度'),
        sa.Column('image_height', sa.Integer(), nullable=True, comment='图像高度'),
        sa.Column('image_version', sa.String(length=100), nullable=True, comment='图像版本'),
        sa.Column('location_precision', sa.Enum('CHARACTER', 'WORD', 'LINE', 'BLOCK', 'PAGE', 'MANUAL_BBOX', name='locationprecision'), server_default='BLOCK', comment='定位精度'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('crop_image_path', sa.String(length=512), nullable=True, comment='裁图路径'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['text_revision_id'], ['text_revisions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_evidence_spans_id'), 'evidence_spans', ['id'], unique=False)
    create_index(op.f('ix_evidence_spans_page_id'), 'evidence_spans', ['page_id'], unique=False)
    create_index(op.f('ix_evidence_spans_text_revision_id'), 'evidence_spans', ['text_revision_id'], unique=False)

    # Create entities table
    create_table('entities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.Enum('PERSON', 'ORGANIZATION', 'PLACE', 'SHIP', 'COMMODITY', name='entitytype'), nullable=False, comment='实体类型'),
        sa.Column('canonical_name', sa.String(length=500), nullable=False, comment='规范名称'),
        sa.Column('canonical_name_zh', sa.String(length=500), nullable=True, comment='中文规范名称'),
        sa.Column('alternative_names', sa.Text(), nullable=True, comment='备选名称（JSON数组）'),
        sa.Column('external_id', sa.String(length=255), nullable=True, comment='外部标识符'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_entities_canonical_name'), 'entities', ['canonical_name'], unique=False)
    create_index(op.f('ix_entities_entity_type'), 'entities', ['entity_type'], unique=False)
    create_index(op.f('ix_entities_external_id'), 'entities', ['external_id'], unique=False)
    create_index(op.f('ix_entities_id'), 'entities', ['id'], unique=False)
    create_index('ix_entities_type_canonical_name', 'entities', ['entity_type', 'canonical_name'], unique=False)

    # Create entity_mentions table
    create_table('entity_mentions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('evidence_span_id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('original_form', sa.String(length=500), nullable=False, comment='原文形式'),
        sa.Column('normalized_form', sa.String(length=500), nullable=True, comment='规范化形式'),
        sa.Column('honorific', sa.String(length=100), nullable=True, comment='敬称'),
        sa.Column('title', sa.String(length=200), nullable=True, comment='职衔'),
        sa.Column('title_abbreviation', sa.String(length=100), nullable=True, comment='职衔缩写'),
        sa.Column('candidate_entity_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='候选实体ID列表'),
        sa.Column('candidate_notes', sa.Text(), nullable=True, comment='身份候选说明'),
        sa.Column('status', sa.Enum('PENDING', 'CANDIDATE', 'CONFIRMED', 'REJECTED', name='mentionstatus'), server_default='PENDING', comment='状态'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='置信度'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['evidence_span_id'], ['evidence_spans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_entity_mentions_entity_id'), 'entity_mentions', ['entity_id'], unique=False)
    create_index(op.f('ix_entity_mentions_evidence_span_id'), 'entity_mentions', ['evidence_span_id'], unique=False)
    create_index(op.f('ix_entity_mentions_id'), 'entity_mentions', ['id'], unique=False)
    create_index(op.f('ix_entity_mentions_original_form'), 'entity_mentions', ['original_form'], unique=False)

    # Create identity_decisions table
    create_table('identity_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mention_id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('basis', sa.Text(), nullable=True, comment='判断依据'),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED', name='decisionstatus'), server_default='PENDING', comment='决策状态'),
        sa.Column('reviewer', sa.String(length=255), nullable=True, comment='审核人'),
        sa.Column('reviewer_type', sa.String(length=50), nullable=True, comment='审核人类型：human/ai'),
        sa.Column('previous_decision_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mention_id'], ['entity_mentions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['previous_decision_id'], ['identity_decisions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_identity_decisions_entity_id'), 'identity_decisions', ['entity_id'], unique=False)
    create_index(op.f('ix_identity_decisions_id'), 'identity_decisions', ['id'], unique=False)
    create_index(op.f('ix_identity_decisions_mention_id'), 'identity_decisions', ['mention_id'], unique=False)

    # Create events table
    create_table('events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False, comment='事件类型'),
        sa.Column('title', sa.String(length=500), nullable=False, comment='事件标题'),
        sa.Column('summary', sa.Text(), nullable=True, comment='事件摘要'),
        sa.Column('date_start', sa.Date(), nullable=True, comment='起始日期'),
        sa.Column('date_end', sa.Date(), nullable=True, comment='结束日期'),
        sa.Column('date_precision', sa.String(length=50), nullable=True, comment='日期精度'),
        sa.Column('location_text', sa.String(length=500), nullable=True, comment='地点文本'),
        sa.Column('location_entity_id', sa.Integer(), nullable=True, comment='规范地点ID'),
        sa.Column('status', sa.Enum('CANDIDATE', 'CONFIRMED', 'DISPUTED', name='eventstatus'), server_default='CANDIDATE', comment='确认状态'),
        sa.Column('confidence', sa.String(length=50), nullable=True, comment='置信度'),
        sa.Column('description', sa.Text(), nullable=True, comment='详细描述'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_events_date_start'), 'events', ['date_start'], unique=False)
    create_index(op.f('ix_events_event_type'), 'events', ['event_type'], unique=False)
    create_index(op.f('ix_events_id'), 'events', ['id'], unique=False)
    create_index('ix_events_type_date', 'events', ['event_type', 'date_start'], unique=False)

    # Create event_mentions table
    create_table('event_mentions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_unit_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=True, comment='事件类型'),
        sa.Column('summary', sa.Text(), nullable=False, comment='事件摘要'),
        sa.Column('mentioned_date_text', sa.String(length=255), nullable=True, comment='提及的日期文本'),
        sa.Column('mentioned_date_start', sa.Date(), nullable=True, comment='提及的起始日期'),
        sa.Column('mentioned_date_end', sa.Date(), nullable=True, comment='提及的结束日期'),
        sa.Column('date_precision', sa.String(length=50), nullable=True, comment='日期精度'),
        sa.Column('location_text', sa.String(length=500), nullable=True, comment='地点文本'),
        sa.Column('status', sa.Enum('CANDIDATE', 'CONFIRMED', 'MERGED', 'REJECTED', name='eventmentionstatus'), server_default='CANDIDATE', comment='状态'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_unit_id'], ['source_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_event_mentions_event_id'), 'event_mentions', ['event_id'], unique=False)
    create_index(op.f('ix_event_mentions_event_type'), 'event_mentions', ['event_type'], unique=False)
    create_index(op.f('ix_event_mentions_id'), 'event_mentions', ['id'], unique=False)
    create_index(op.f('ix_event_mentions_source_unit_id'), 'event_mentions', ['source_unit_id'], unique=False)

    # Create participations table
    create_table('participations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=200), nullable=False, comment='角色'),
        sa.Column('role_description', sa.Text(), nullable=True, comment='角色描述'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_participations_entity_id'), 'participations', ['entity_id'], unique=False)
    create_index(op.f('ix_participations_event_id'), 'participations', ['event_id'], unique=False)
    create_index(op.f('ix_participations_id'), 'participations', ['id'], unique=False)
    create_index(op.f('ix_participations_role'), 'participations', ['role'], unique=False)

    # Create event_relations table
    create_table('event_relations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_event_id', sa.Integer(), nullable=False),
        sa.Column('target_event_id', sa.Integer(), nullable=False),
        sa.Column('relation_type', sa.Enum('REPLY_TO', 'FOLLOWS', 'SAME_EVENT_CANDIDATE', 'CAUSES', 'PART_OF', 'RELATED_TO', name='eventrelationtype'), nullable=False, comment='关系类型'),
        sa.Column('description', sa.Text(), nullable=True, comment='关系描述'),
        sa.Column('confidence', sa.String(length=50), nullable=True, comment='置信度'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_event_relations_id'), 'event_relations', ['id'], unique=False)
    create_index(op.f('ix_event_relations_relation_type'), 'event_relations', ['relation_type'], unique=False)
    create_index(op.f('ix_event_relations_source_event_id'), 'event_relations', ['source_event_id'], unique=False)
    create_index(op.f('ix_event_relations_target_event_id'), 'event_relations', ['target_event_id'], unique=False)

    # Create assertions table
    create_table('assertions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_entity_id', sa.Integer(), nullable=False),
        sa.Column('predicate', sa.String(length=200), nullable=False, comment='谓词'),
        sa.Column('object_entity_id', sa.Integer(), nullable=True),
        sa.Column('object_literal', sa.Text(), nullable=True, comment='字面值宾语'),
        sa.Column('object_type', sa.String(length=50), nullable=True, comment='宾语类型'),
        sa.Column('valid_from', sa.Date(), nullable=True, comment='有效起始时间'),
        sa.Column('valid_to', sa.Date(), nullable=True, comment='有效结束时间'),
        sa.Column('temporal_precision', sa.String(length=50), nullable=True, comment='时间精度'),
        sa.Column('source_type', sa.Enum('EXTRACTED', 'MANUAL', 'EXTERNAL', 'INFERRED', name='sourcetype'), server_default='EXTRACTED', comment='来源类型'),
        sa.Column('status', sa.Enum('CANDIDATE', 'VERIFIED', 'DISPUTED', 'REJECTED', name='assertionstatus'), server_default='CANDIDATE', comment='验证状态'),
        sa.Column('confidence', sa.String(length=50), nullable=True, comment='置信度'),
        sa.Column('extra_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='附加元数据'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['object_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_assertions_id'), 'assertions', ['id'], unique=False)
    create_index(op.f('ix_assertions_object_entity_id'), 'assertions', ['object_entity_id'], unique=False)
    create_index(op.f('ix_assertions_predicate'), 'assertions', ['predicate'], unique=False)
    create_index(op.f('ix_assertions_subject_entity_id'), 'assertions', ['subject_entity_id'], unique=False)

    # Create assertion_evidences table
    create_table('assertion_evidences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assertion_id', sa.Integer(), nullable=False),
        sa.Column('evidence_span_id', sa.Integer(), nullable=False),
        sa.Column('relation', sa.Enum('SUPPORTS', 'CONTRADICTS', 'MENTIONS', 'UNCERTAIN', name='evidencerelation'), nullable=False, server_default='SUPPORTS', comment='关系类型'),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assertion_id'], ['assertions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['evidence_span_id'], ['evidence_spans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_assertion_evidences_assertion_id'), 'assertion_evidences', ['assertion_id'], unique=False)
    create_index(op.f('ix_assertion_evidences_evidence_span_id'), 'assertion_evidences', ['evidence_span_id'], unique=False)
    create_index(op.f('ix_assertion_evidences_id'), 'assertion_evidences', ['id'], unique=False)

    # Create review_decisions table
    create_table('review_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.Enum('ENTITY_MENTION', 'IDENTITY_DECISION', 'EVENT_MENTION', 'EVENT', 'ASSERTION', 'SOURCE_UNIT', 'TEXT_REVISION', name='reviewtargettype'), nullable=False, comment='目标类型'),
        sa.Column('target_id', sa.Integer(), nullable=False, comment='目标ID'),
        sa.Column('decision', sa.Enum('APPROVED', 'REJECTED', 'NEEDS_REVISION', 'FLAGGED', name='reviewdecisiontype'), nullable=False, comment='决策'),
        sa.Column('reason', sa.Text(), nullable=True, comment='理由'),
        sa.Column('reviewer', sa.String(length=255), nullable=False, comment='操作者'),
        sa.Column('reviewer_role', sa.String(length=100), nullable=True, comment='操作者角色'),
        sa.Column('previous_decision_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True, comment='备注'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['previous_decision_id'], ['review_decisions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_review_decisions_created_at'), 'review_decisions', ['created_at'], unique=False)
    create_index(op.f('ix_review_decisions_id'), 'review_decisions', ['id'], unique=False)
    create_index(op.f('ix_review_decisions_target_id'), 'review_decisions', ['target_id'], unique=False)
    create_index(op.f('ix_review_decisions_target_type'), 'review_decisions', ['target_type'], unique=False)

    # Create extraction_runs table
    create_table('extraction_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('input_version_ids', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='输入版本集合（text_revision_ids）'),
        sa.Column('input_hash', sa.String(length=64), nullable=True, comment='输入内容hash'),
        sa.Column('model_name', sa.String(length=200), nullable=True, comment='模型名称'),
        sa.Column('model_version', sa.String(length=100), nullable=True, comment='模型版本'),
        sa.Column('prompt_template', sa.Text(), nullable=True, comment='提示词模板'),
        sa.Column('schema_version', sa.String(length=100), nullable=True, comment='Schema版本'),
        sa.Column('parameters', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='抽取参数'),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='extractionstatus'), server_default='PENDING', comment='状态'),
        sa.Column('output_summary', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='输出摘要'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('cost_tokens_input', sa.Integer(), nullable=True, comment='输入token数'),
        sa.Column('cost_tokens_output', sa.Integer(), nullable=True, comment='输出token数'),
        sa.Column('cost_amount', sa.Float(), nullable=True, comment='成本金额'),
        sa.Column('batch_id', sa.String(length=100), nullable=True, comment='批次ID'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_extraction_runs_batch_id'), 'extraction_runs', ['batch_id'], unique=False)
    create_index(op.f('ix_extraction_runs_created_at'), 'extraction_runs', ['created_at'], unique=False)
    create_index(op.f('ix_extraction_runs_document_id'), 'extraction_runs', ['document_id'], unique=False)
    create_index(op.f('ix_extraction_runs_id'), 'extraction_runs', ['id'], unique=False)
    create_index(op.f('ix_extraction_runs_input_hash'), 'extraction_runs', ['input_hash'], unique=False)
    create_index(op.f('ix_extraction_runs_status'), 'extraction_runs', ['status'], unique=False)

    # Create search_chunks table
    create_table('search_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_unit_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False, comment='文书片段内容'),
        sa.Column('content_hash', sa.String(length=64), nullable=False, comment='内容hash'),
        sa.Column('content_language', sa.String(length=10), nullable=True, comment='内容语言'),
        sa.Column('content_type', sa.String(length=50), nullable=True, comment='内容类型'),
        sa.Column('evidence_span_ids', sa.Text(), nullable=True, comment='对应证据集合（逗号分隔的ID）'),
        sa.Column('embedding', Vector(1536), nullable=True, comment='向量嵌入'),
        sa.Column('embedding_model', sa.String(length=200), nullable=True, comment='嵌入模型'),
        sa.Column('status', sa.Enum('PENDING', 'INDEXED', 'INVALIDATED', name='chunkstatus'), server_default='PENDING', comment='索引状态'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_unit_id'], ['source_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    create_index(op.f('ix_search_chunks_content_hash'), 'search_chunks', ['content_hash'], unique=False)
    create_index(op.f('ix_search_chunks_id'), 'search_chunks', ['id'], unique=False)
    create_index(op.f('ix_search_chunks_source_unit_id'), 'search_chunks', ['source_unit_id'], unique=False)
    create_index(op.f('ix_search_chunks_status'), 'search_chunks', ['status'], unique=False)
    create_index('ix_search_chunks_status_indexed', 'search_chunks', ['status', 'indexed_at'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('ix_search_chunks_status_indexed', table_name='search_chunks')
    op.drop_index(op.f('ix_search_chunks_status'), table_name='search_chunks')
    op.drop_index(op.f('ix_search_chunks_source_unit_id'), table_name='search_chunks')
    op.drop_index(op.f('ix_search_chunks_id'), table_name='search_chunks')
    op.drop_index(op.f('ix_search_chunks_content_hash'), table_name='search_chunks')
    op.drop_table('search_chunks')

    op.drop_index(op.f('ix_extraction_runs_status'), table_name='extraction_runs')
    op.drop_index(op.f('ix_extraction_runs_input_hash'), table_name='extraction_runs')
    op.drop_index(op.f('ix_extraction_runs_id'), table_name='extraction_runs')
    op.drop_index(op.f('ix_extraction_runs_document_id'), table_name='extraction_runs')
    op.drop_index(op.f('ix_extraction_runs_created_at'), table_name='extraction_runs')
    op.drop_index(op.f('ix_extraction_runs_batch_id'), table_name='extraction_runs')
    op.drop_table('extraction_runs')

    op.drop_index(op.f('ix_review_decisions_target_type'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_target_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_created_at'), table_name='review_decisions')
    op.drop_table('review_decisions')

    op.drop_index(op.f('ix_assertion_evidences_id'), table_name='assertion_evidences')
    op.drop_index(op.f('ix_assertion_evidences_evidence_span_id'), table_name='assertion_evidences')
    op.drop_index(op.f('ix_assertion_evidences_assertion_id'), table_name='assertion_evidences')
    op.drop_table('assertion_evidences')

    op.drop_index(op.f('ix_assertions_subject_entity_id'), table_name='assertions')
    op.drop_index(op.f('ix_assertions_predicate'), table_name='assertions')
    op.drop_index(op.f('ix_assertions_object_entity_id'), table_name='assertions')
    op.drop_index(op.f('ix_assertions_id'), table_name='assertions')
    op.drop_table('assertions')

    op.drop_index(op.f('ix_event_relations_target_event_id'), table_name='event_relations')
    op.drop_index(op.f('ix_event_relations_source_event_id'), table_name='event_relations')
    op.drop_index(op.f('ix_event_relations_relation_type'), table_name='event_relations')
    op.drop_index(op.f('ix_event_relations_id'), table_name='event_relations')
    op.drop_table('event_relations')

    op.drop_index(op.f('ix_participations_role'), table_name='participations')
    op.drop_index(op.f('ix_participations_id'), table_name='participations')
    op.drop_index(op.f('ix_participations_event_id'), table_name='participations')
    op.drop_index(op.f('ix_participations_entity_id'), table_name='participations')
    op.drop_table('participations')

    op.drop_index(op.f('ix_event_mentions_source_unit_id'), table_name='event_mentions')
    op.drop_index(op.f('ix_event_mentions_id'), table_name='event_mentions')
    op.drop_index(op.f('ix_event_mentions_event_type'), table_name='event_mentions')
    op.drop_index(op.f('ix_event_mentions_event_id'), table_name='event_mentions')
    op.drop_table('event_mentions')

    op.drop_index('ix_events_type_date', table_name='events')
    op.drop_index(op.f('ix_events_id'), table_name='events')
    op.drop_index(op.f('ix_events_event_type'), table_name='events')
    op.drop_index(op.f('ix_events_date_start'), table_name='events')
    op.drop_table('events')

    op.drop_index(op.f('ix_identity_decisions_mention_id'), table_name='identity_decisions')
    op.drop_index(op.f('ix_identity_decisions_id'), table_name='identity_decisions')
    op.drop_index(op.f('ix_identity_decisions_entity_id'), table_name='identity_decisions')
    op.drop_table('identity_decisions')

    op.drop_index(op.f('ix_entity_mentions_original_form'), table_name='entity_mentions')
    op.drop_index(op.f('ix_entity_mentions_id'), table_name='entity_mentions')
    op.drop_index(op.f('ix_entity_mentions_evidence_span_id'), table_name='entity_mentions')
    op.drop_index(op.f('ix_entity_mentions_entity_id'), table_name='entity_mentions')
    op.drop_table('entity_mentions')

    op.drop_index('ix_entities_type_canonical_name', table_name='entities')
    op.drop_index(op.f('ix_entities_id'), table_name='entities')
    op.drop_index(op.f('ix_entities_external_id'), table_name='entities')
    op.drop_index(op.f('ix_entities_entity_type'), table_name='entities')
    op.drop_index(op.f('ix_entities_canonical_name'), table_name='entities')
    op.drop_table('entities')

    op.drop_index(op.f('ix_evidence_spans_text_revision_id'), table_name='evidence_spans')
    op.drop_index(op.f('ix_evidence_spans_page_id'), table_name='evidence_spans')
    op.drop_index(op.f('ix_evidence_spans_id'), table_name='evidence_spans')
    op.drop_table('evidence_spans')

    op.drop_index(op.f('ix_text_revisions_id'), table_name='text_revisions')
    op.drop_index(op.f('ix_text_revisions_created_at'), table_name='text_revisions')
    op.drop_index(op.f('ix_text_revisions_content_hash'), table_name='text_revisions')
    op.drop_index(op.f('ix_text_revisions_block_id'), table_name='text_revisions')
    op.drop_table('text_revisions')

    op.drop_index(op.f('ix_source_unit_spans_source_unit_id'), table_name='source_unit_spans')
    op.drop_index(op.f('ix_source_unit_spans_id'), table_name='source_unit_spans')
    op.drop_index(op.f('ix_source_unit_spans_block_id'), table_name='source_unit_spans')
    op.drop_table('source_unit_spans')

    op.drop_index(op.f('ix_source_units_normalized_date_start'), table_name='source_units')
    op.drop_index(op.f('ix_source_units_id'), table_name='source_units')
    op.drop_index(op.f('ix_source_units_archival_metadata_id'), table_name='source_units')
    op.drop_table('source_units')

    op.drop_index(op.f('ix_archival_metadata_id'), table_name='archival_metadata')
    op.drop_index(op.f('ix_archival_metadata_document_id'), table_name='archival_metadata')
    op.drop_index(op.f('ix_archival_metadata_archival_reference'), table_name='archival_metadata')
    op.drop_table('archival_metadata')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS chunkstatus')
    op.execute('DROP TYPE IF EXISTS extractionstatus')
    op.execute('DROP TYPE IF EXISTS reviewdecisiontype')
    op.execute('DROP TYPE IF EXISTS reviewtargettype')
    op.execute('DROP TYPE IF EXISTS evidencerelation')
    op.execute('DROP TYPE IF EXISTS assertionstatus')
    op.execute('DROP TYPE IF EXISTS sourcetype')
    op.execute('DROP TYPE IF EXISTS eventrelationtype')
    op.execute('DROP TYPE IF EXISTS eventmentionstatus')
    op.execute('DROP TYPE IF EXISTS eventstatus')
    op.execute('DROP TYPE IF EXISTS decisionstatus')
    op.execute('DROP TYPE IF EXISTS mentionstatus')
    op.execute('DROP TYPE IF EXISTS entitytype')
    op.execute('DROP TYPE IF EXISTS locationprecision')
    op.execute('DROP TYPE IF EXISTS texttype')
    op.execute('DROP TYPE IF EXISTS dateprecision')
    op.execute('DROP TYPE IF EXISTS segmentationstatus')
    op.execute('DROP TYPE IF EXISTS sourceunittype')
    op.execute('DROP TYPE IF EXISTS completenessstatus')

    # Drop pgvector extension
    op.execute('DROP EXTENSION IF EXISTS vector')
