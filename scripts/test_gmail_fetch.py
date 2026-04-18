import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.gmail import GmailService


if __name__ == "__main__":
    service = GmailService()
    messages = service.fetch_recent_messages(days=90, limit=10)
    print(f"Fetched {len(messages)} messages")
    for idx, msg in enumerate(messages, start=1):
        preview = (msg.get("body", "") or "")[:80].replace("\n", " ")
        print(f"{idx}. {msg.get('subject', '(no subject)')} :: {preview}")
