from services.memory.database import Base, engine

# Import all models so SQLAlchemy knows about them
from services.memory.models import MemoryModel

print("Creating database...")

Base.metadata.create_all(bind=engine)

print("Database created successfully.")