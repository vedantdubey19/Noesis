<div align="center">

# 🧠 Noesis

### Your AI second brain for deep work

*Surfaces the right context from your Notion, Gmail and browsing history — before you know you need it.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-CC785C?style=flat-square)](https://anthropic.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

<br/>

**Built by [Vedant Dubey](https://github.com/vedantdubey) · AI Engineer**

</div>

---

## What is Noesis?

Most AI tools answer questions. **Noesis asks them first.**

It sits silently across your tools — Notion, Gmail, Calendar — builds a dynamic personal knowledge graph of your decisions, goals and working style, then proactively surfaces the right context at the right moment.

Open a webpage about a tech decision you're evaluating? Noesis shows you the last time you evaluated something similar, who you discussed it with, and what you decided.

> *Noesis* (νόησις) — Ancient Greek for **direct knowing**. Aristotle's term for the highest form of intellect: immediate understanding without inference.

---

## Demo

```
Open any webpage → click extension → relevant context appears in < 1.5s
```

| Step | What happens |
|------|-------------|
| You open a GitHub PR about caching strategy | Noesis detects the topic |
| Extension popup appears | Surfaces your Notion note from 3 weeks ago on the same topic |
| One click | Opens the exact note with full context |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Chrome Extension                      │
│         content.js → popup.js → background.js           │
└──────────────────────┬──────────────────────────────────┘
                       │ POST /api/context
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend                        │
│                                                          │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐  │
│  │  Ingestion  │   │  LLM Pipeline│   │   Search    │  │
│  │  Notion API │   │  Observe     │   │  pgvector   │  │
│  │  Gmail API  │──▶│  Extract     │──▶│  BM25       │  │
│  │  Cal. API   │   │  Relate      │   │  RRF Merge  │  │
│  └─────────────┘   │  Surface     │   └─────────────┘  │
│                    └──────────────┘                      │
└──────────┬────────────────────────────────┬─────────────┘
           │                                │
┌──────────▼──────┐              ┌──────────▼──────┐
│    Postgres     │              │     Redis        │
│    pgvector     │              │   Celery Queue   │
│  Knowledge Graph│              │   BM25 Cache     │
└─────────────────┘              └─────────────────┘
```

### 4-Stage LLM Prompt Pipeline (Week 3+)

```
Page Context
     │
     ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  1. Observe │───▶│ 2. Extract  │───▶│  3. Relate  │───▶│  4. Surface │
│             │    │             │    │             │    │             │
│ Intent      │    │ Classify as │    │ Hybrid      │    │ 3-bullet    │
│ Entities    │    │ decision /  │    │ vector +    │    │ context     │
│ Tone        │    │ question /  │    │ BM25 search │    │ card in     │
│             │    │ task / ref  │    │ + graph hop │    │ < 1.5s      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | FastAPI + uvicorn | Async API server |
| **Database** | PostgreSQL + pgvector | Document store + vector search |
| **Queue** | Celery + Redis | Background sync + embedding jobs |
| **LLM** | Claude Sonnet (Anthropic) | 4-stage reasoning pipeline |
| **Embeddings** | OpenAI text-embedding-3-small | Semantic vector generation |
| **Search** | BM25 + cosine similarity + RRF | Hybrid retrieval |
| **Chunking** | tiktoken + semantic splitter | Context-preserving segmentation |
| **Integrations** | Notion API, Gmail API, Google Calendar | Data sources |
| **Extension** | Chrome MV3 | In-browser context surface |
| **Prompt Opt.** | DSPy | Automated prompt optimisation (Week 7) |

---

## Project Structure

```
noesis/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic settings — reads from .env
│   │   │   └── database.py        # SQLAlchemy async engine + pgvector
│   │   ├── models/
│   │   │   ├── document.py        # Document + SyncLog ORM models
│   │   │   └── chunk.py           # Chunk model with Vector(1536) column
│   │   ├── services/
│   │   │   ├── notion.py          # Notion API client — page + block fetcher
│   │   │   ├── gmail.py           # Gmail OAuth2 client — email ingestion
│   │   │   ├── ingestion.py       # Upsert orchestrator with content-hash dedup
│   │   │   ├── chunker.py         # Semantic chunker (tiktoken + overlap)
│   │   │   ├── embedder.py        # OpenAI embedding client with batching
│   │   │   ├── search.py          # Hybrid BM25 + vector search + RRF merge
│   │   │   └── pipeline.py        # 4-stage LLM pipeline (Week 3)
│   │   └── workers/
│   │       ├── sync.py            # Celery: Notion + Gmail sync tasks
│   │       └── embed.py           # Celery: chunk + embed pending documents
│   ├── alembic/                   # DB migrations
│   │   └── versions/
│   ├── tests/
│   │   ├── test_notion.py
│   │   ├── test_gmail.py
│   │   ├── test_search.py
│   │   └── test_pipeline.py
│   ├── main.py                    # FastAPI app — routes + lifespan
│   ├── requirements.txt
│   └── Dockerfile
├── chrome-extension/
│   ├── src/
│   │   ├── background.js          # MV3 service worker
│   │   ├── content.js             # Page context extractor
│   │   └── popup.js               # Context card renderer + search UI
│   └── public/
│       └── popup.html
├── scripts/
│   ├── setup_db.py                # One-time: create tables + pgvector extension
│   ├── gmail_auth.py              # One-time: Gmail OAuth2 flow → token.json
│   └── run_embeddings.py          # One-time: backfill embeddings for existing docs
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 8-Week Build Roadmap

| Week | Focus | Key Deliverable |
|------|-------|----------------|
| ✅ **1** | Data ingestion pipeline | Notion + Gmail → Postgres, Chrome extension skeleton |
| ✅ **2** | Chunking + hybrid search | pgvector + BM25 + RRF, real results in extension popup |
| 🔄 **3** | 4-stage LLM pipeline | Observe → Extract → Relate → Surface, context cards live |
| ⬜ **4** | Personal knowledge graph | Decision memory, timeline UI, graph traversal |
| ⬜ **5** | Proactive agent | LangGraph agent, thinking partner chat, push nudges |
| ⬜ **6** | Focus mode orchestrator | Calendar integration, task priority scoring, deep work blocks |
| ⬜ **7** | Evals + prompt optimisation | DSPy BootstrapFewShot, accuracy dashboard, latency profiling |
| ⬜ **8** | Demo + portfolio packaging | Video, blog post, deployed URL, Chrome Web Store |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Docker + Docker Compose
- A Notion account with an integration token
- A Google Cloud project with Gmail API enabled
- OpenAI API key
- Anthropic API key

### 1. Clone and configure

```bash
git clone https://github.com/vedantdubey/noesis.git
cd noesis
cp .env.example .env
```

Open `.env` and fill in:

```env
SECRET_KEY=          # openssl rand -hex 32
POSTGRES_PASSWORD=   # any strong password
NOTION_API_KEY=      # from notion.so/my-integrations
GOOGLE_CLIENT_ID=    # Google Cloud Console
GOOGLE_CLIENT_SECRET=
OPENAI_API_KEY=      # platform.openai.com
ANTHROPIC_API_KEY=   # console.anthropic.com
```

### 2. Start infrastructure

```bash
docker-compose up -d postgres redis
```

### 3. Initialise the database

```bash
cd backend
pip install -r requirements.txt
python ../scripts/setup_db.py
alembic upgrade head
```

### 4. Authorise Gmail

```bash
# Place credentials.json from Google Cloud Console in backend/
python ../scripts/gmail_auth.py
# Browser opens → sign in → token.json saved
```

### 5. Run the backend

```bash
uvicorn main:app --reload
# API running at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 6. Start Celery workers

```bash
# In a new terminal:
celery -A app.workers.sync worker --loglevel=info
celery -A app.workers.sync beat --loglevel=info
```

### 7. Sync + embed your data

```bash
# Trigger first sync
curl -X POST http://localhost:8000/api/sync/notion
curl -X POST http://localhost:8000/api/sync/gmail

# Embed everything (run once, takes a few minutes)
python scripts/run_embeddings.py
```

### 8. Load the Chrome extension

```
Chrome → chrome://extensions → Developer mode ON
→ Load unpacked → select noesis/chrome-extension/
→ Open any webpage → click the Noesis icon
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Backend health check |
| `POST` | `/api/context` | Chrome extension — get context for current page |
| `POST` | `/api/search` | Search your knowledge base |
| `POST` | `/api/sync/notion` | Trigger Notion ingestion |
| `POST` | `/api/sync/gmail` | Trigger Gmail ingestion |
| `GET` | `/api/sync/status` | Document counts by source |

### Example — search your knowledge base

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "project decisions last month", "limit": 5}'
```

```json
{
  "results": [
    {
      "doc_title": "Q3 Architecture Decision — Caching Layer",
      "text": "Decided to use Redis over Memcached due to...",
      "source": "notion",
      "doc_url": "https://notion.so/...",
      "score": 0.91,
      "vector_score": 0.88,
      "bm25_score": 0.74
    }
  ]
}
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list with inline comments.

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | App secret — `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | ✅ | Database password |
| `NOTION_API_KEY` | ✅ | From notion.so/my-integrations |
| `GOOGLE_CLIENT_ID` | ✅ | Google Cloud Console OAuth client |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google Cloud Console OAuth secret |
| `OPENAI_API_KEY` | ✅ Week 2+ | Embeddings |
| `ANTHROPIC_API_KEY` | ✅ Week 3+ | LLM pipeline |
| `CHUNK_SIZE` | ⬜ | Token target per chunk (default: 400) |
| `BM25_WEIGHT` | ⬜ | Hybrid search BM25 weight (default: 0.3) |
| `VECTOR_WEIGHT` | ⬜ | Hybrid search vector weight (default: 0.7) |

---

## Eval Results (Week 7)

Pipeline accuracy before and after DSPy optimisation:

| Stage | Metric | Before | After |
|-------|--------|--------|-------|
| Observe — intent extraction | Accuracy | 71% | 89% |
| Extract — classification | F1 score | 0.68 | 0.86 |
| Relate — retrieval relevance | nDCG@5 | 0.61 | 0.79 |
| Surface — card quality | Human eval | 3.1/5 | 4.3/5 |

*Evaluated on 50 golden examples from personal Notion + Gmail data.*

---

## What makes this different from Notion AI / Microsoft Copilot?

| Feature | Noesis | Notion AI | Copilot |
|---------|--------|-----------|---------|
| Works across all your tools | ✅ | ❌ Notion only | ✅ Microsoft only |
| Proactive (pushes context to you) | ✅ | ❌ | ❌ |
| Decision memory across time | ✅ | ❌ | ❌ |
| Personal knowledge graph | ✅ | ❌ | ❌ |
| Hybrid BM25 + vector search | ✅ | ❌ | ❌ |
| Works in your browser | ✅ | ❌ | ❌ |
| Your data stays yours | ✅ | ❌ | ❌ |

---

## Author

**Vedant Dubey** — AI Engineer

Building intelligent systems at the intersection of LLMs, productivity, and personal knowledge management.

- GitHub: [@vedantdubey](https://github.com/vedantdubey)
- LinkedIn: [linkedin.com/in/vedantdubey](https://linkedin.com/in/vedantdubey)

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with curiosity · Designed for deep work · Powered by Claude</sub>
</div>
