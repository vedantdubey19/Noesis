import time

from tqdm import tqdm

from app.core.database import SessionLocal
from app.models.document import Document
from app.workers.embed import embed_pending_documents


def main() -> None:
    started = time.time()
    db = SessionLocal()
    try:
        total_documents = db.query(Document).count()
    finally:
        db.close()

    # Show progress bar for visibility, then execute one-shot backfill task.
    for _ in tqdm(range(total_documents), desc="Scanning documents"):
        pass

    result = embed_pending_documents(document_ids=None)
    elapsed = int(time.time() - started)
    mins = elapsed // 60
    secs = elapsed % 60
    print(
        f"Embedded {result['documents']} documents → {result['chunks']} chunks in {mins}m {secs:02d}s"
    )


if __name__ == "__main__":
    main()
