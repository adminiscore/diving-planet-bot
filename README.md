# 🤿 Diving Planet Bot

AI-powered customer service chatbot for **Diving Planet Cartagena** — Colombia's first PADI 5 Star Dive Center with 30 years of experience in the Rosario Islands.

## Architecture

```
Customer (WhatsApp / Web) → Chatwoot → FastAPI Webhook → Decision Tree (Phase 1)
                                                        → LangGraph Agents (Phase 2)
                                                        → Owner Dashboard
```

**Phase 1** — Predefined decision tree (no LLM, zero cost)
- Language selection (ES/EN)
- Guided flow: Tours → Experience level → Service → Location → Booking link
- Escalation to human via Chatwoot


**Phase 2** — LangGraph multi-agent system
- Supervisor agent (GPT-4o-mini) for free-text queries
- RAG agent for knowledge base (pgvector)
- Booking agent for Roverd integration
- Escalation agent with Chatwoot handoff

## Tech Stack

| Component | Technology |
|---|---|
| Agents | LangGraph + LangChain |
| LLM | GPT-4o-mini (OpenAI) |
| API | FastAPI |
| Inbox / Live Chat | Chatwoot (self-hosted) |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| Observability | LangSmith |
| Channel | WhatsApp Business API |

## Environments

The project uses **3 environments**: dev (local), pre (staging VPS), pro (production VPS).

| Environment | Where | Compose file | `.env` file |
|---|---|---|---|
| **dev** | Your PC (Windows) | `docker-compose.yml` | `.env.dev` |
| **pre** | VPS | `docker-compose.vps.yml` | `.env.pre` |
| **pro** | VPS (same server) | `docker-compose.vps.yml` | `.env.pro` |

> **Important for the team**: `.env.*` files contain secrets and are **NOT** committed to git.
> Each developer creates their own from the example templates:

```bash
# After git pull, copy the example and fill in your API keys
cp .env.dev.example .env.dev
# Edit .env.dev with your own OPENAI_API_KEY and other secrets
```

The `.example` files are tracked in git and serve as documentation for required variables.

## Quick Start (DEV — Local)

### Prerequisites
- Python 3.11+ ([download](https://www.python.org/downloads/))
- Docker Desktop ([download](https://www.docker.com/products/docker-desktop/))
- OpenAI API key
- LangSmith API key (optional, for tracing)

### Setup

```bash
# Clone and enter the project
git clone https://github.com/YOUR_USER/diving-planet-bot.git
cd diving-planet-bot

# 1. Create your environment file (this file is gitignored — never commit it!)
cp .env.dev.example .env.dev
# Edit .env.dev with your OPENAI_API_KEY and other secrets

# 2. Start infrastructure (PostgreSQL + Redis only)
docker compose up -d

# 3. (Optional) Start Chatwoot locally
docker compose --profile chatwoot up -d

# 4. Create Chatwoot database (if using Chatwoot)
docker exec dp-dev-postgres psql -U postgres -c "CREATE DATABASE chatwoot_dev;"

# 5. Install Python dependencies
pip install -e ".[dev]"

# 6. Load knowledge base embeddings
python -m scripts.load_embeddings

# 7. Run tests
pytest

# 8. Start the bot API
ENV_FILE=.env.dev python -m src.main
```

### Access (DEV)

| Service | URL |
|---|---|
| Bot API | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Chatwoot | http://localhost:3000 |

## Deploy (VPS — PRE + PRO)

```bash
# On the VPS, after cloning the repo:

# 1. Create environment files with strong passwords
cp .env.pre.example .env.pre
cp .env.pro.example .env.pro
# Edit both with real API keys and strong passwords

# 2. Start all services (Chatwoot has its own dedicated Postgres/Redis,
#    independent of dp-pre-* and dp-pro-*)
docker compose -f docker-compose.vps.yml up -d --build

# 3. Load embeddings (staging)
docker exec dp-pre-bot python -m scripts.load_embeddings

# 4. Load embeddings (production)
docker exec dp-pro-bot python -m scripts.load_embeddings

# 5. Verify
curl https://pre.divingplanet.org/health
curl https://api.divingplanet.org/health
```

### Access (VPS)

| Service | URL |
|---|---|
| Staging API | https://pre.divingplanet.org |
| Production API | https://api.divingplanet.org |
| Chatwoot | https://chatwoot.divingplanet.org |

## Project Structure

```
src/
├── main.py              # FastAPI entry point
├── config.py            # Environment config (pydantic-settings)
├── flows/
│   └── decision_tree.py # Phase 1: predefined guided flow
├── agents/
│   ├── supervisor.py    # Phase 2: LangGraph orchestrator
│   ├── rag_agent.py     # Phase 2: knowledge base retrieval
│   ├── booking_agent.py # Phase 2: Roverd booking integration
│   └── escalation.py    # Human handoff via Chatwoot
├── channels/
│   └── chatwoot.py      # Chatwoot webhook handler
├── knowledge/
│   └── loader.py        # Knowledge base loader
└── db/
    └── models.py        # SQLAlchemy models

data/knowledge_base/
├── services.json        # Service catalog
├── faqs.json            # Frequently asked questions
└── policies.json        # Business policies

tests/
└── test_decision_tree.py
```

## License

Private — Diving Planet Cartagena
