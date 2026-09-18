"""
Database Manager
"""

from packages.common import logger
from services.memory.database import Base, engine


class DatabaseManager:

    def initialize(self):
        logger.info("Initializing Database...")

        # Import state models so SQLAlchemy registers them before create_all
        import packages.database.state_models  # noqa: F401

        Base.metadata.create_all(bind=engine)

        logger.info("Database Ready")


database_manager = DatabaseManager()