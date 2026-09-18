"""
Nova state store — SQLite schemas for Phase 1.

Tables: events (via event bus), entities, memory_episodic,
memory_semantic, memory_procedural, audit_log.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
    Boolean,
    Index,
)
from sqlalchemy.sql import func

from services.memory.database import Base


class EntityModel(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(100), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    attributes = Column(JSON, default=dict)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    source = Column(String(200))

    __table_args__ = (
        Index("idx_entity_type_name", "entity_type", "name"),
    )


class EpisodicMemory(Base):
    __tablename__ = "memory_episodic"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(200), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    detail = Column(JSON, default=dict)
    speaker_id = Column(String(100))
    emotion = Column(String(50))
    importance = Column(Float, default=0.5)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    correlation_id = Column(String(100), index=True)


class SemanticMemory(Base):
    __tablename__ = "memory_semantic"

    id = Column(Integer, primary_key=True)
    key = Column(String(500), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    category = Column(String(100), index=True)
    confidence = Column(Float, default=1.0)
    source = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProceduralMemory(Base):
    __tablename__ = "memory_procedural"

    id = Column(Integer, primary_key=True)
    action = Column(String(200), nullable=False, index=True)
    trigger_pattern = Column(Text)
    steps = Column(JSON, default=list)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    last_used = Column(DateTime(timezone=True))
    learned_from = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(200), nullable=False, index=True)
    source = Column(String(200), nullable=False)
    action = Column(String(200), nullable=False)
    detail = Column(JSON, default=dict)
    speaker_id = Column(String(100))
    severity = Column(Integer, default=0)
    correlation_id = Column(String(100), index=True)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
