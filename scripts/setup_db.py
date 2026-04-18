import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import engine
from app.models.document import Base
from app.models.chunk import Chunk  # noqa: F401


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")
