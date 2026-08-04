"""
Database Models
"""

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy.sql import func

from services.memory.database import Base


class MemoryModel(Base):

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True)

    key = Column(String(255), unique=True, nullable=False)

    value = Column(String(5000), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )