"""
models.py – SQLAlchemy ORM models for Nimbus Insight.
ProcessingJob stores all metadata for each CSV upload and classification run.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, Enum as SAEnum
from sqlalchemy.types import TypeDecorator, TEXT
from database import Base
import json
import enum


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JSONType(TypeDecorator):
    """Custom SQLAlchemy type that serialises Python dicts/lists to JSON text in SQLite."""

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(32), nullable=True, index=True)  # MD5 of file content
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False)

    # Results
    report_text = Column(Text, nullable=True)
    error_log = Column(Text, nullable=True)
    ticket_count = Column(Integer, default=0)
    escalated_count = Column(Integer, default=0)

    # KPI JSON blobs
    category_counts = Column(JSONType, default=dict)
    urgency_counts = Column(JSONType, default=dict)
    cache_snapshot = Column(JSONType, default=dict)
