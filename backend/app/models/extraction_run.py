"""Extraction run model for tracking extraction processes."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, JSON, Float
from sqlalchemy.orm import relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.document import Document


class ExtractionStatus(str, enum.Enum):
    """Extraction run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExtractionRun(Base):
    """
    Extraction run tracking for reproducibility.

    Records input versions, model, schema, and outputs.
    """

    __tablename__ = "extraction_runs"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Input configuration
    input_version_ids = Column(JSON, nullable=True, comment="输入版本集合（text_revision_ids）")
    input_hash = Column(String(64), nullable=True, index=True, comment="输入内容hash")

    # Model and schema
    model_name = Column(String(200), nullable=True, comment="模型名称")
    model_version = Column(String(100), nullable=True, comment="模型版本")
    prompt_template = Column(Text, nullable=True, comment="提示词模板")
    schema_version = Column(String(100), nullable=True, comment="Schema版本")

    # Parameters
    parameters = Column(JSON, nullable=True, comment="抽取参数")

    # Status and results
    status = Column(Enum(ExtractionStatus), default=ExtractionStatus.PENDING, index=True, comment="状态")
    output_summary = Column(JSON, nullable=True, comment="输出摘要")
    error_message = Column(Text, nullable=True, comment="错误信息")

    # Cost tracking
    cost_tokens_input = Column(Integer, nullable=True, comment="输入token数")
    cost_tokens_output = Column(Integer, nullable=True, comment="输出token数")
    cost_amount = Column(Float, nullable=True, comment="成本金额")

    # Batch information
    batch_id = Column(String(100), nullable=True, index=True, comment="批次ID")

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    document = relationship("Document", back_populates="extraction_runs")

    def __repr__(self) -> str:
        return f"<ExtractionRun(id={self.id}, document_id={self.document_id}, status={self.status})>"
