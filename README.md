# Noesis

Data ingestion pipeline for Week 1:

- Sources: Notion + Gmail + browser page context
- Storage: Postgres (`documents` table)
- API: FastAPI with bearer auth header guard
- Background jobs: Celery + Redis (30-minute Notion sync)
- Client: Chrome extension popup to sync current page

## Project Structure

```
noesis/
├── backend/
│   ├── app/
│   │   ├── api/              # Route handlers + auth dependency
│   │   ├── core/             # Settings + database session
│   │   ├── services/         # Notion / Gmail / ingestion logic
│   │   ├── models/           # SQLAlchemy ORM models
│   │   └── workers/          # Celery tasks
│   ├── tests/                # Week 1 tests
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── chrome-extension/
├── scripts/
├── docker-compose.yml
└── .env.example
```

## One-Time Setup (Day 1)

1. Copy env file:
   - `cp .env.example .env`
2. Start infra:
   - `docker-compose up -d`
3. Create virtual env + install deps:
   - `cd backend`
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
4. Create database tables:
   - `python ../scripts/setup_db.py`
5. Verify Postgres connection:
   - `psql "postgresql://noesis:noesis@localhost:5432/noesis" -c "\dt"`

## Day 2: Notion Integration

1. Create Notion integration and set `NOTION_API_KEY` in `.env`.
2. Share relevant Notion pages/databases with your integration.
3. Run quick fetch test:
   - `python ../scripts/test_notion_fetch.py`
4. Trigger ingestion via API:
   - `curl -X POST http://localhost:8000/api/sync/notion -H "Authorization: Bearer dev-secret-token"`

What gets stored:
- page metadata
- page blocks (`blocks/{page_id}/children`)
- discovered workspace databases from search

## Day 3: Gmail Integration

1. Enable Gmail API in Google Cloud.
2. Save OAuth client file as `backend/credentials.json`.
3. Run first fetch (opens browser OAuth once and writes `backend/token.json`):
   - `python ../scripts/test_gmail_fetch.py`
4. Trigger ingestion via API:
   - `curl -X POST http://localhost:8000/api/sync/gmail -H "Authorization: Bearer dev-secret-token"`

What gets stored:
- message id + subject
- plaintext body (prefers `text/plain`, falls back to HTML-to-text)

## Day 4: API + Chrome Extension

Run API:
- `uvicorn main:app --reload --host 0.0.0.0 --port 8000`

API endpoints (all require auth header):
- `GET /api/health`
- `POST /api/context`
- `POST /api/sync/notion`
- `POST /api/sync/gmail`
- `POST /api/sync/all`

Chrome extension:
1. Open `chrome://extensions`
2. Enable Developer Mode
3. Load unpacked: `chrome-extension/`
4. Open popup, set:
   - API URL: `http://localhost:8000/api/context`
   - API Token: same as `API_AUTH_TOKEN` in `.env`
5. Click **Sync Current Page** on any webpage

Expected popup result:
- `Data synced for <url>`

## Day 5: Worker + Tests + End-to-End

Run Celery worker and beat:
- `celery -A app.workers.sync worker --beat --loglevel=info`

What it does:
- runs Notion ingestion every 30 minutes through Redis broker

Run tests:
- `pytest -q`

Suggested E2E check:
1. Start API + worker
2. Open any Gmail page in browser
3. Use extension popup to sync page context
4. Confirm popup success and row inserted in `documents`

## Notes

- `documents` has uniqueness on `(source, source_id)` to prevent duplicate rows.
- The app is scaffolded for Week 1 build velocity; for production, add retries, structured logging, secrets management, and robust pagination.

## Week 2: Chunking, Embeddings, Hybrid Search

Added in Week 2:
- semantic chunking via `SemanticChunker` (`tiktoken`)
- OpenAI embeddings via `EmbeddingService` (`text-embedding-3-small`)
- hybrid retrieval via `HybridSearchService` (pgvector cosine + BM25 + RRF)
- new `chunks` table and embedding worker
- `/api/search` endpoint and `/api/context` context cards

### Alembic setup

```bash
cd backend
alembic init alembic
alembic revision --autogenerate -m "add chunks table"
alembic upgrade head
```

### Backfill embeddings

```bash
cd backend
python scripts/run_embeddings.py
```

### Search verify

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-secret-token" \
  -d '{"query": "project decisions last month", "limit": 5}'
```
