"""
State store repository — read/write access to entities, memory tiers, and audit log.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from services.memory.database import get_session
from packages.database.state_models import (
    EntityModel,
    EpisodicMemory,
    SemanticMemory,
    ProceduralMemory,
    AuditLog,
)


class StateStore:

    # --- Entities ---

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        attributes: Dict[str, Any] | None = None,
        source: str = "",
    ) -> int:
        session = get_session()
        try:
            existing = (
                session.query(EntityModel)
                .filter_by(entity_type=entity_type, name=name)
                .first()
            )
            if existing:
                if attributes:
                    merged = dict(existing.attributes or {})
                    merged.update(attributes)
                    existing.attributes = merged
                existing.source = source or existing.source
                session.commit()
                return existing.id
            entity = EntityModel(
                entity_type=entity_type,
                name=name,
                attributes=attributes or {},
                source=source,
            )
            session.add(entity)
            session.commit()
            return entity.id
        finally:
            session.close()

    def get_entities(
        self,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        session = get_session()
        try:
            q = session.query(EntityModel)
            if entity_type:
                q = q.filter_by(entity_type=entity_type)
            q = q.order_by(desc(EntityModel.last_seen)).limit(limit)
            return [
                {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "name": e.name,
                    "attributes": e.attributes,
                    "first_seen": str(e.first_seen),
                    "last_seen": str(e.last_seen),
                    "source": e.source,
                }
                for e in q.all()
            ]
        finally:
            session.close()

    # --- Episodic Memory ---

    def store_episode(
        self,
        event_type: str,
        summary: str,
        detail: Dict[str, Any] | None = None,
        speaker_id: str | None = None,
        emotion: str | None = None,
        importance: float = 0.5,
        correlation_id: str | None = None,
    ) -> int:
        session = get_session()
        try:
            episode = EpisodicMemory(
                event_type=event_type,
                summary=summary,
                detail=detail or {},
                speaker_id=speaker_id,
                emotion=emotion,
                importance=importance,
                correlation_id=correlation_id,
            )
            session.add(episode)
            session.commit()
            return episode.id
        finally:
            session.close()

    def recent_episodes(self, limit: int = 20) -> List[Dict[str, Any]]:
        session = get_session()
        try:
            rows = (
                session.query(EpisodicMemory)
                .order_by(desc(EpisodicMemory.created_at))
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "summary": r.summary,
                    "detail": r.detail,
                    "speaker_id": r.speaker_id,
                    "importance": r.importance,
                    "created_at": str(r.created_at),
                }
                for r in rows
            ]
        finally:
            session.close()

    # --- Semantic Memory ---

    def store_fact(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "",
    ) -> None:
        session = get_session()
        try:
            existing = session.query(SemanticMemory).filter_by(key=key).first()
            if existing:
                existing.value = value
                existing.confidence = confidence
                existing.category = category
                existing.source = source or existing.source
            else:
                session.add(SemanticMemory(
                    key=key, value=value, category=category,
                    confidence=confidence, source=source,
                ))
            session.commit()
        finally:
            session.close()

    def recall_fact(self, key: str) -> Optional[str]:
        session = get_session()
        try:
            row = session.query(SemanticMemory).filter_by(key=key).first()
            return row.value if row else None
        finally:
            session.close()

    # --- Procedural Memory ---

    def store_procedure(
        self,
        action: str,
        steps: List[Dict[str, Any]],
        trigger_pattern: str = "",
        learned_from: str = "",
    ) -> int:
        session = get_session()
        try:
            proc = ProceduralMemory(
                action=action,
                trigger_pattern=trigger_pattern,
                steps=steps,
                learned_from=learned_from,
            )
            session.add(proc)
            session.commit()
            return proc.id
        finally:
            session.close()

    def record_procedure_outcome(self, action: str, success: bool) -> None:
        session = get_session()
        try:
            proc = session.query(ProceduralMemory).filter_by(action=action).first()
            if proc:
                if success:
                    proc.success_count = (proc.success_count or 0) + 1
                else:
                    proc.fail_count = (proc.fail_count or 0) + 1
                from sqlalchemy.sql import func
                proc.last_used = func.now()
                session.commit()
        finally:
            session.close()

    # --- Audit Log ---

    def audit(
        self,
        event_type: str,
        source: str,
        action: str,
        detail: Dict[str, Any] | None = None,
        speaker_id: str | None = None,
        severity: int = 0,
        correlation_id: str | None = None,
        success: bool = True,
    ) -> None:
        session = get_session()
        try:
            session.add(AuditLog(
                event_type=event_type,
                source=source,
                action=action,
                detail=detail or {},
                speaker_id=speaker_id,
                severity=severity,
                correlation_id=correlation_id,
                success=success,
            ))
            session.commit()
        finally:
            session.close()

    def recent_audit(self, limit: int = 50) -> List[Dict[str, Any]]:
        session = get_session()
        try:
            rows = (
                session.query(AuditLog)
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "source": r.source,
                    "action": r.action,
                    "detail": r.detail,
                    "severity": r.severity,
                    "success": r.success,
                    "created_at": str(r.created_at),
                }
                for r in rows
            ]
        finally:
            session.close()


state_store = StateStore()
