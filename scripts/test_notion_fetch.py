import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.notion import NotionService


if __name__ == "__main__":
    service = NotionService()
    pages = service.search_pages(limit=5)
    print(f"Fetched {len(pages)} pages")
    for idx, page in enumerate(pages, start=1):
        print(f"{idx}. {page.get('id')}")
